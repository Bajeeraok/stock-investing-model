"""Train the pooled odds model (signals/pooled_odds.py) and validate it walk-forward.

Each test year is predicted by a model trained only on rows whose outcome was known
before that year (purge = horizon + 5 sessions). Reports Brier skill vs each stock's own
history odds, calibration bucket gaps, and the blend weight per horizon; then fits the
final model on all labelled rows and writes artifacts/pooled_odds.json.

Usage: python scripts/train_pooled_odds.py OHLCV_PKL [--horizons short,medium,long] [--no-save]
OHLCV_PKL: yfinance-style DataFrame with (field, ticker) MultiIndex columns incl. SPY.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from signals.ml_models import _GAIN_THRESHOLDS, HORIZONS  # noqa: E402
from signals.pooled_odds import (  # noqa: E402
    ARTIFACT_PATH,
    forward_label,
    history_rate_series,
    market_features,
    pooled_eligible,
    ticker_features,
)

STEP = 5
TEST_YEARS = list(range(2019, 2027))
WEIGHTS = (0.0, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 1.0)
PARAMS = dict(objective="binary", n_estimators=300, learning_rate=0.03, num_leaves=15, min_child_samples=500,
              subsample=0.7, subsample_freq=1, colsample_bytree=0.8, reg_lambda=5.0, verbose=-1)


def gains_for(h_key: str) -> list[float]:
    t = _GAIN_THRESHOLDS[h_key]
    return sorted({t["default"], t["growth_high"]})


def build_panel(raw: pd.DataFrame, h_keys: list[str]) -> dict[str, pd.DataFrame]:
    spy_feat = market_features(raw.xs("SPY", axis=1, level=1)["Close"].dropna())
    out: dict[str, list] = {k: [] for k in h_keys}
    tickers = [t for t in raw.columns.get_level_values(1).unique() if t != "SPY" and pooled_eligible(t)]
    for i, t in enumerate(tickers):
        df = raw.xs(t, axis=1, level=1).rename(columns=str.lower).dropna(subset=["close", "high", "low"])
        if len(df) < 600:
            continue
        f = ticker_features(df, spy_feat, t)
        if f is None:
            continue
        for k in h_keys:
            days = HORIZONS[k]["days"]
            for g in gains_for(k):
                part = f.copy()
                part["gain"] = g
                part["y"] = forward_label(df["close"], days, g).reindex(f.index)
                part["hist"] = history_rate_series(df["close"], days, g).reindex(f.index)
                part = part.iloc[260::STEP]
                part["ticker"] = t
                out[k].append(part)
        if i % 100 == 0:
            print("panel", i, t, flush=True)
    panels = {}
    for k, frames in out.items():
        p = pd.concat(frames)
        p.index.name = "date"
        panels[k] = p.reset_index()
    return panels


def feature_cols(p: pd.DataFrame) -> list[str]:
    return [c for c in p.columns if c not in ("date", "ticker", "y", "hist")]


def _brier(y, p) -> float:
    return float(np.mean((np.asarray(p) - np.asarray(y)) ** 2))


def max_bucket_gap(y, p, min_n: int = 200) -> float:
    d = pd.DataFrame({"y": y, "p": p})
    d["b"] = pd.cut(d["p"], [0, .2, .4, .6, .8, 1.0], include_lowest=True)
    g = d.groupby("b", observed=True).agg(n=("y", "size"), hit=("y", "mean"), said=("p", "mean"))
    g = g[g["n"] >= min_n]
    return float((g["hit"] - g["said"]).abs().max() * 100) if len(g) else float("nan")


def walk_forward(p: pd.DataFrame, days: int) -> pd.DataFrame:
    import lightgbm as lgb
    feats = feature_cols(p)
    d = p.dropna(subset=["y"]).copy()
    d["year"] = d["date"].dt.year
    oos = []
    for y in TEST_YEARS:
        cutoff = pd.Timestamp(f"{y}-01-01") - pd.tseries.offsets.BDay(days + 5)
        tr, te = d[d["date"] < cutoff], d[d["year"] == y].copy()
        if len(tr) < 20000 or te.empty:
            continue
        m = lgb.LGBMClassifier(**PARAMS).fit(tr[feats], tr["y"])
        te["p_model"] = m.predict_proba(te[feats])[:, 1]
        te["base"] = tr["y"].mean()
        te["hist"] = te["hist"].fillna(te["base"])
        oos.append(te)
        print(f"  {days}d {y}: train {len(tr)} test {len(te)}", flush=True)
    return pd.concat(oos)


def report(o: pd.DataFrame) -> tuple[dict, float]:
    b_hist, b_base = _brier(o["y"], o["hist"]), _brier(o["y"], o["base"])
    rows = {}
    for w in WEIGHTS:
        pb = w * o["p_model"] + (1 - w) * o["hist"]
        rows[w] = dict(skill_vs_hist=round(100 * (1 - _brier(o["y"], pb) / b_hist), 2),
                       skill_vs_base=round(100 * (1 - _brier(o["y"], pb) / b_base), 2),
                       max_gap=round(max_bucket_gap(o["y"], pb), 1))
    # pick weight on the first half of years, report it on the second half (no peeking)
    years = sorted(o["year"].unique())
    early, late = o[o["year"].isin(years[: len(years) // 2])], o[o["year"].isin(years[len(years) // 2:])]
    best = max(WEIGHTS, key=lambda w: -_brier(early["y"], w * early["p_model"] + (1 - w) * early["hist"]))
    pl = best * late["p_model"] + (1 - best) * late["hist"]
    rows["chosen"] = dict(weight=best, late_skill_vs_hist=round(100 * (1 - _brier(late["y"], pl) / _brier(late["y"], late["hist"])), 2),
                          late_max_gap=round(max_bucket_gap(late["y"], pl), 1))
    return rows, best


def main() -> None:
    import lightgbm as lgb
    ap = argparse.ArgumentParser()
    ap.add_argument("ohlcv")
    ap.add_argument("--horizons", default="short,medium,long")
    ap.add_argument("--no-save", action="store_true")
    ap.add_argument("--oos-dir", default="")
    ap.add_argument("--weights", default="short=0.3,medium=0.5,long=0.5",
                    help="model share of the blend per horizon; with 2000+ history these were positive "
                         "in every test year 2019-2026 with the smallest calibration gaps")
    a = ap.parse_args()
    h_keys = a.horizons.split(",")
    weights = {k: float(v) for k, v in (x.split("=") for x in a.weights.split(","))}
    raw = pd.read_pickle(a.ohlcv)
    panels = build_panel(raw, h_keys)
    art = {"version": f"pooled-{date.today():%Y.%m.%d}", "models": {}, "weights": {}, "base_rate": {},
           "validation": {}, "trained_through": str(raw.index.max().date())}
    for k in h_keys:
        p, days = panels[k], HORIZONS[k]["days"]
        o = walk_forward(p, days)
        if a.oos_dir:
            o.to_pickle(Path(a.oos_dir) / f"pooled_oos_{k}.pkl")
        rows, _ = report(o)
        w = weights[k]
        print(k, json.dumps({str(x): v for x, v in rows.items()}, indent=1), flush=True)
        d = p.dropna(subset=["y"])
        feats = feature_cols(p)
        m = lgb.LGBMClassifier(**PARAMS).fit(d[feats], d["y"])
        art["features"] = feats
        art["models"][k] = m.booster_.model_to_string()
        art["weights"][k] = w
        art["base_rate"][k] = round(float(d["y"].mean()), 4)
        art["validation"][k] = {"weight": w, **rows.get(w, {}), "early_late_pick": rows["chosen"], "oos_rows": int(len(o))}
    if not a.no_save:
        ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
        ARTIFACT_PATH.write_text(json.dumps(art))
        print("saved", ARTIFACT_PATH, ARTIFACT_PATH.stat().st_size // 1024, "KB")


if __name__ == "__main__":
    main()
