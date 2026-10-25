"""
Pooled cross-sectional alpha model with purged walk-forward validation.

One LightGBM per (horizon, label) trained across the whole universe:
  - ``beat``: P(ticker beats SPY by more than costs over the horizon)
  - ``tb``:   P(ATR target hit before ATR stop within the horizon)
plus LightGBM quantile models of the absolute forward return (10th/50th/90th
percentile) used for target / stretch / stop ranges.

Validation: expanding-window walk-forward with a purge gap equal to the horizon,
retrained every ``step_days``; the most recent ``holdout_days`` are locked and
scored once by a model that never saw them. Probabilities are isotonic-calibrated
on out-of-sample walk-forward predictions. Promotion gates decide whether the
live app may use the model.
"""
from __future__ import annotations

import math
import pickle
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_ARTIFACT = BACKEND_ROOT / "data" / "alpha" / "pooled_model.pkl"

HORIZONS = {"short": 20, "medium": 60}
LABELS = ("beat", "tb")
QUANTILES = (0.1, 0.5, 0.9)


@dataclass
class WalkForwardConfig:
    min_train_days: int = 756
    step_days: int = 126
    holdout_days: int = 252
    cost: float = 0.003
    top_frac: float = 0.10
    n_estimators: int = 300
    learning_rate: float = 0.03
    num_leaves: int = 31
    min_child_samples: int = 200
    max_train_rows: int = 400_000
    gates: dict[str, float] = field(
        default_factory=lambda: {"min_auc": 0.52, "min_top_net_excess_pct": 0.0, "min_ic": 0.01}
    )


def label_cols(h: str) -> dict[str, str]:
    return {"beat": f"y_beat_{h}", "tb": f"y_tb_{h}", "fwd_ret": f"fwd_ret_{h}", "fwd_exc": f"fwd_exc_{h}"}


def feature_columns(panel: pd.DataFrame) -> list[str]:
    return [c for c in panel.columns if not c.startswith(("y_", "fwd_")) and panel[c].dtype.kind in "fi"]


def _lgb_clf(cfg: WalkForwardConfig):
    import lightgbm as lgb

    return lgb.LGBMClassifier(
        n_estimators=cfg.n_estimators,
        learning_rate=cfg.learning_rate,
        num_leaves=cfg.num_leaves,
        min_child_samples=cfg.min_child_samples,
        subsample=0.8,
        subsample_freq=1,
        colsample_bytree=0.8,
        random_state=42,
        verbose=-1,
    )


def _lgb_quantile(alpha: float, cfg: WalkForwardConfig):
    import lightgbm as lgb

    return lgb.LGBMRegressor(
        objective="quantile",
        alpha=alpha,
        n_estimators=max(100, cfg.n_estimators // 2),
        learning_rate=cfg.learning_rate,
        num_leaves=15,
        min_child_samples=cfg.min_child_samples,
        subsample=0.8,
        subsample_freq=1,
        random_state=42,
        verbose=-1,
    )


def _sample(df: pd.DataFrame, n: int) -> pd.DataFrame:
    return df.sample(n=n, random_state=42) if len(df) > n else df


def walk_forward_folds(dates: list, horizon: int, cfg: WalkForwardConfig):
    """Yield (train_dates, test_dates) — expanding train, purge = horizon bars, pre-holdout only."""
    usable = dates[: max(0, len(dates) - cfg.holdout_days)]
    start = cfg.min_train_days
    while start + horizon < len(usable):
        train = usable[: start]
        test = usable[start + horizon: min(len(usable), start + horizon + cfg.step_days)]
        if not test:
            break
        yield train, test
        start += cfg.step_days


def evaluate_predictions(df: pd.DataFrame, prob_col: str, h: str, cfg: WalkForwardConfig) -> dict[str, Any]:
    """AUC, rank IC and top-bucket net excess return vs SPY (percent) on scored rows."""
    from sklearn.metrics import roc_auc_score

    lc = label_cols(h)
    d = df.dropna(subset=[prob_col, lc["fwd_exc"]])
    if d.empty:
        return {"n": 0}
    out: dict[str, Any] = {"n": int(len(d))}
    y = d[lc["beat"]]
    if y.nunique() == 2:
        out["auc_beat"] = round(float(roc_auc_score(y, d[prob_col])), 4)
    ics = d.groupby(level="date").apply(
        lambda g: g[prob_col].rank().corr(g[lc["fwd_exc"]].rank()) if len(g) >= 10 else np.nan
    )
    out["ic_mean"] = round(float(ics.mean()), 4) if ics.notna().any() else None
    q = d.groupby(level="date")[prob_col].rank(pct=True)
    top = d[q >= 1 - cfg.top_frac]
    bot = d[q <= cfg.top_frac]
    out["top_mean_excess_pct"] = round(100 * float(top[lc["fwd_exc"]].mean()), 3)
    out["top_net_excess_pct"] = round(100 * (float(top[lc["fwd_exc"]].mean()) - cfg.cost), 3)
    out["top_beat_rate_pct"] = round(100 * float((top[lc["fwd_exc"]] > cfg.cost).mean()), 2)
    out["bottom_mean_excess_pct"] = round(100 * float(bot[lc["fwd_exc"]].mean()), 3)
    out["base_beat_rate_pct"] = round(100 * float(y.mean()), 2)
    return out


def passes_gates(m: dict[str, Any], cfg: WalkForwardConfig) -> tuple[bool, list[str]]:
    g = cfg.gates
    fails = []
    if (m.get("auc_beat") or 0) < g["min_auc"]:
        fails.append(f"auc_beat {m.get('auc_beat')} < {g['min_auc']}")
    if (m.get("top_net_excess_pct") if m.get("top_net_excess_pct") is not None else -math.inf) <= g["min_top_net_excess_pct"]:
        fails.append(f"top_net_excess_pct {m.get('top_net_excess_pct')} <= {g['min_top_net_excess_pct']}")
    if (m.get("ic_mean") or 0) < g["min_ic"]:
        fails.append(f"ic_mean {m.get('ic_mean')} < {g['min_ic']}")
    return (not fails), fails


def _fit_isotonic(p: np.ndarray, y: np.ndarray):
    from sklearn.isotonic import IsotonicRegression

    iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    iso.fit(p, y)
    return iso


def train_horizon(panel: pd.DataFrame, h: str, cfg: WalkForwardConfig) -> dict[str, Any]:
    horizon = HORIZONS[h]
    lc = label_cols(h)
    feats = feature_columns(panel)
    data = panel.dropna(subset=[lc["beat"], lc["fwd_exc"]])
    dates = sorted(data.index.get_level_values("date").unique())
    oos_parts = []
    folds = 0
    for train_d, test_d in walk_forward_folds(dates, horizon, cfg):
        tr = _sample(data.loc[(slice(train_d[0], train_d[-1])), :], cfg.max_train_rows)
        te = data.loc[(slice(test_d[0], test_d[-1])), :]
        part = te[[lc["beat"], lc["tb"], lc["fwd_exc"]]].copy()
        for lab in LABELS:
            col = lc[lab]
            trl = tr.dropna(subset=[col])
            if trl[col].nunique() < 2:
                continue
            m = _lgb_clf(cfg).fit(trl[feats], trl[col])
            part[f"p_{lab}"] = m.predict_proba(te[feats])[:, 1]
        oos_parts.append(part)
        folds += 1
    if not oos_parts:
        return {"error": "not enough history for walk-forward"}
    oos = pd.concat(oos_parts)
    wf_metrics = evaluate_predictions(oos, "p_beat", h, cfg) if "p_beat" in oos else {"n": 0}

    calibrators = {}
    for lab in LABELS:
        pc = f"p_{lab}"
        if pc in oos:
            d = oos.dropna(subset=[pc, lc[lab]])
            calibrators[lab] = _fit_isotonic(d[pc].to_numpy(), d[lc[lab]].to_numpy())

    # Final models: everything before the locked holdout (minus purge).
    cut = len(dates) - cfg.holdout_days
    pre = data.loc[(slice(dates[0], dates[max(0, cut - horizon - 1)])), :]
    hold = data.loc[(slice(dates[cut], dates[-1])), :] if cut < len(dates) else data.iloc[0:0]
    pre_s = _sample(pre, cfg.max_train_rows)
    models = {}
    for lab in LABELS:
        d = pre_s.dropna(subset=[lc[lab]])
        if d[lc[lab]].nunique() == 2:
            models[lab] = _lgb_clf(cfg).fit(d[feats], d[lc[lab]])
    qmodels = {}
    dq = pre_s.dropna(subset=[lc["fwd_ret"]])
    for a in QUANTILES:
        qmodels[a] = _lgb_quantile(a, cfg).fit(dq[feats], dq[lc["fwd_ret"]])

    holdout_metrics: dict[str, Any] = {"n": 0}
    if len(hold) and "beat" in models:
        hp = hold[[lc["beat"], lc["tb"], lc["fwd_exc"], lc["fwd_ret"]]].copy()
        raw = models["beat"].predict_proba(hold[feats])[:, 1]
        hp["p_beat"] = calibrators["beat"].predict(raw) if "beat" in calibrators else raw
        holdout_metrics = evaluate_predictions(hp, "p_beat", h, cfg)
        qlo, qhi = qmodels[0.1].predict(hold[feats]), qmodels[0.9].predict(hold[feats])
        inside = (hp[lc["fwd_ret"]] >= qlo) & (hp[lc["fwd_ret"]] <= qhi)
        holdout_metrics["q10_q90_coverage_pct"] = round(100 * float(inside.mean()), 2)
        if "tb" in calibrators and "tb" in models:
            ptb = calibrators["tb"].predict(models["tb"].predict_proba(hold[feats])[:, 1])
            ytb = hold[lc["tb"]]
            ok = ytb.notna().to_numpy()
            holdout_metrics["tb_brier"] = round(float(np.mean((ptb[ok] - ytb.to_numpy()[ok]) ** 2)), 4)
    ok_wf, fails_wf = passes_gates(wf_metrics, cfg)
    ok_ho, fails_ho = passes_gates(holdout_metrics, cfg)
    return {
        "horizon_days": horizon,
        "features": feats,
        "models": models,
        "calibrators": calibrators,
        "quantile_models": qmodels,
        "walk_forward_folds": folds,
        "walk_forward_metrics": wf_metrics,
        "holdout_metrics": holdout_metrics,
        "promoted": bool(ok_wf and ok_ho),
        "gate_failures": fails_wf + [f"holdout: {f}" for f in fails_ho],
        "trained_through": str(pre.index.get_level_values("date").max().date()),
    }


def train_all(panel: pd.DataFrame, cfg: WalkForwardConfig | None = None, horizons=None) -> dict[str, Any]:
    cfg = cfg or WalkForwardConfig()
    out = {"created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "cost": cfg.cost, "horizons": {}}
    for h in horizons or HORIZONS:
        out["horizons"][h] = train_horizon(panel, h, cfg)
    return out


def save_artifact(art: dict[str, Any], path: str | Path | None = None) -> Path:
    p = Path(path or DEFAULT_ARTIFACT)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "wb") as f:
        pickle.dump(art, f)
    return p


def load_artifact(path: str | Path | None = None) -> dict[str, Any] | None:
    p = Path(path or DEFAULT_ARTIFACT)
    if not p.exists():
        return None
    with open(p, "rb") as f:
        return pickle.load(f)


def predict_latest(art: dict[str, Any], panel: pd.DataFrame, *, require_promoted: bool = True) -> pd.DataFrame:
    """Score the latest date in ``panel``: calibrated P(beat SPY), P(target first), return quantiles."""
    last = panel.index.get_level_values("date").max()
    x = panel.xs(last, level="date")
    res = pd.DataFrame(index=x.index)
    for h, hm in (art.get("horizons") or {}).items():
        if "models" not in hm or (require_promoted and not hm.get("promoted")):
            continue
        X = x.reindex(columns=hm["features"])
        for lab, m in hm["models"].items():
            p = m.predict_proba(X)[:, 1]
            cal = hm["calibrators"].get(lab)
            res[f"p_{lab}_{h}"] = cal.predict(p) if cal is not None else p
        for a, qm in hm["quantile_models"].items():
            res[f"ret_q{int(a * 100)}_{h}"] = qm.predict(X)
    res["as_of"] = str(pd.Timestamp(last).date())
    return res
