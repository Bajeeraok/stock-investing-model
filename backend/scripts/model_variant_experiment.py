"""Compare per-ticker LightGBM (production setup) vs pooled LightGBM, plus calibration
variants (expanding isotonic / Platt, shrink toward per-ticker history), walk-forward."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.model_label_experiment import TEST_YEARS, _auc  # noqa: E402
from signals.ml_models import build_features  # noqa: E402

OUT = Path("/home/ubuntu/model_exp")
N_PER_TICKER = 120


def pooled_oos(panel: pd.DataFrame, h: int) -> pd.DataFrame:
    import lightgbm as lgb
    ycol, hcol = f"y_prod{h}", f"hist_prod{h}"
    feats = [c for c in panel.columns if c not in ("date", "ticker") and not c.startswith(("y_", "hist_"))]
    d = panel.dropna(subset=[ycol]).copy()
    d["year"] = d["date"].dt.year
    res = []
    for y in TEST_YEARS:
        cutoff = pd.Timestamp(f"{y}-01-01") - pd.tseries.offsets.BDay(h + 5)
        tr, te = d[d["date"] < cutoff], d[d["year"] == y].copy()
        if len(tr) < 20000 or te.empty:
            continue
        m = lgb.LGBMClassifier(n_estimators=300, learning_rate=0.03, num_leaves=15, min_child_samples=500,
                               subsample=0.7, subsample_freq=1, colsample_bytree=0.8, reg_lambda=5.0, verbose=-1)
        m.fit(tr[feats], tr[ycol])
        te["p_pool"] = m.predict_proba(te[feats])[:, 1]
        te["base"] = tr[ycol].mean()
        te["hist"] = te[hcol].fillna(te["base"])
        res.append(te[["date", "ticker", "year", ycol, "p_pool", "hist", "base"]].rename(columns={ycol: "y"}))
    return pd.concat(res)


def per_ticker_oos(raw: pd.DataFrame, tickers: list[str], h: int, keep: set) -> pd.DataFrame:
    import lightgbm as lgb
    hk = "short" if h == 20 else "medium"
    res = []
    for t in tickers:
        df = raw.xs(t, axis=1, level=1).rename(columns=str.lower).dropna(subset=["close"])
        f = build_features(df, t, hk)
        if f is None:
            continue
        reg = f.pop("regime_label")
        y = f.pop("target")
        X = f.select_dtypes(include=[np.number])
        for yr in TEST_YEARS:
            cutoff = pd.Timestamp(f"{yr}-01-01") - pd.tseries.offsets.BDay(h + 5)
            trm = (X.index < cutoff) & y.notna()
            tem = (X.index.year == yr) & y.notna()
            if trm.sum() < 300 or tem.sum() == 0 or y[trm].nunique() < 2:
                continue
            freq = reg[trm].value_counts(normalize=True)
            w = reg[trm].map({k: 1 / max(v, 0.05) for k, v in freq.items()}).to_numpy()
            m = lgb.LGBMClassifier(n_estimators=500, learning_rate=0.01, num_leaves=31, feature_fraction=0.8,
                                   bagging_fraction=0.8, bagging_freq=5, min_child_samples=20,
                                   random_state=42, verbose=-1)
            m.fit(X[trm], y[trm], sample_weight=w / w.mean())
            p = pd.DataFrame({"date": X.index[tem], "p_tick": m.predict_proba(X[tem])[:, 1]})
            p["ticker"] = t
            res.append(p)
    out = pd.concat(res)
    return out[[(d, t) in keep for d, t in zip(out["date"], out["ticker"])]]


def expanding_cal(o: pd.DataFrame, col: str, kind: str) -> pd.Series:
    from sklearn.isotonic import IsotonicRegression
    from sklearn.linear_model import LogisticRegression
    out = pd.Series(np.nan, index=o.index)
    for yr in sorted(o["year"].unique()):
        past, cur = o[o["year"] < yr], o["year"] == yr
        if len(past) < 5000:
            continue
        if kind == "iso":
            m = IsotonicRegression(out_of_bounds="clip", y_min=0.01, y_max=0.99).fit(past[col], past["y"])
            out[cur] = m.predict(o.loc[cur, col])
        else:
            lg = lambda p: np.log(np.clip(p, 1e-3, 1 - 1e-3) / (1 - np.clip(p, 1e-3, 1 - 1e-3)))
            m = LogisticRegression(C=1.0).fit(lg(past[col].to_numpy()).reshape(-1, 1), past["y"])
            out[cur] = m.predict_proba(lg(o.loc[cur, col].to_numpy()).reshape(-1, 1))[:, 1]
    return out


def score(o: pd.DataFrame, cols: list[str]) -> dict:
    y = o["y"].to_numpy()
    bh = float(np.mean((o["hist"] - y) ** 2))
    bb = float(np.mean((o["base"] - y) ** 2))
    r = {"n": int(len(o)), "base_rate": round(float(y.mean()), 4)}
    for c in cols:
        b = float(np.mean((o[c] - y) ** 2))
        rk = o.groupby("date")[c].rank(pct=True)
        r[c] = {"auc": round(_auc(y, o[c]) or 0, 4), "skill_vs_hist_pct": round(100 * (1 - b / bh), 2),
                "skill_vs_base_pct": round(100 * (1 - b / bb), 2),
                "top_dec": round(float(o.loc[rk >= .9, "y"].mean()), 3),
                "max_bucket_gap_pts": max_gap(o[c], o["y"])}
    return r


def max_gap(p: pd.Series, y: pd.Series) -> float:
    b = pd.cut(p, [0, .2, .4, .6, .8, 1.01], right=False)
    g = pd.DataFrame({"p": p, "y": y, "b": b}).groupby("b", observed=True).agg(p=("p", "mean"), y=("y", "mean"), n=("y", "size"))
    g = g[g["n"] >= 200]
    return round(float((g["p"] - g["y"]).abs().max() * 100), 1) if len(g) else 0.0


def main() -> None:
    panel = pd.read_pickle(OUT / "panel.pkl")
    raw = pd.read_pickle("/home/ubuntu/sbt_full/ohlcv.pkl")
    rng = np.random.default_rng(7)
    tick = sorted(rng.choice(sorted(panel["ticker"].unique()), N_PER_TICKER, replace=False).tolist())
    results = {}
    for h in (20, 60):
        po = pooled_oos(panel, h)
        keep = set(zip(po["date"], po["ticker"]))
        pt = per_ticker_oos(raw, tick, h, keep)
        print("per-ticker rows", h, len(pt), flush=True)
        o = po.merge(pt, on=["date", "ticker"], how="left").reset_index(drop=True)
        for c in ("p_pool", "p_tick"):
            o[c + "_iso"] = expanding_cal(o.dropna(subset=[c]), c, "iso").reindex(o.index)
            o[c + "_platt"] = expanding_cal(o.dropna(subset=[c]), c, "platt").reindex(o.index)
        for w in (0.3, 0.5, 0.7):
            o[f"blend_raw_{w}"] = w * o["p_pool"] + (1 - w) * o["hist"]
            o[f"blend_platt_{w}"] = w * o["p_pool_platt"] + (1 - w) * o["hist"]
        o = o[o["year"] >= 2019]
        all_cols = ["hist", "p_pool", "p_pool_iso", "p_pool_platt"] + [c for c in o.columns if c.startswith("blend_")]
        results[f"pooled_all_{h}"] = score(o.dropna(subset=["p_pool_platt"]), all_cols)
        sub = o.dropna(subset=["p_tick", "p_tick_platt", "p_pool_platt"])
        results[f"subset_{h}"] = score(sub, ["hist", "p_tick", "p_tick_platt", "p_pool", "p_pool_platt", "blend_platt_0.5"])
        o.to_pickle(OUT / f"oos_{h}.pkl")
        print(json.dumps({k: v for k, v in results.items() if k.endswith(str(h))}, indent=1), flush=True)
    (OUT / "variants.json").write_text(json.dumps(results, indent=1))


if __name__ == "__main__":
    main()
