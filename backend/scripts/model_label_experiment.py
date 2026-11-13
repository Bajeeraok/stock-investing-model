"""Walk-forward test: pooled LightGBM vs per-ticker history odds, for the production
label (close after H days >= +N%) and a plan label (target hit before stop within H).

Usage: python scripts/model_label_experiment.py [ohlcv.pkl] [out.json]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from signals.ml_models import build_features, get_target_gain  # noqa: E402

PLAN = {20: (2.0, 4.0), 60: (3.0, 6.0)}  # (stop ATRs, target ATRs) → R:R 2
STEP = 5
TEST_YEARS = list(range(2018, 2027))


def _atr_pct(df: pd.DataFrame) -> pd.Series:
    pc = df["close"].shift(1)
    tr = pd.concat([df["high"] - df["low"], (df["high"] - pc).abs(), (df["low"] - pc).abs()], axis=1).max(axis=1)
    return tr.rolling(14, min_periods=10).mean() / df["close"]


def plan_label(df: pd.DataFrame, h: int, stop_atr: float, tgt_atr: float) -> pd.Series:
    c, hi, lo = (df[k].to_numpy(float) for k in ("close", "high", "low"))
    atr = _atr_pct(df).to_numpy(float)
    stp, tgt = c * (1 - stop_atr * atr), c * (1 + tgt_atr * atr)
    n = len(c)
    first_t = np.full(n, np.inf)
    first_s = np.full(n, np.inf)
    for k in range(1, h + 1):
        hik = np.full(n, np.nan); hik[:-k] = hi[k:]
        lok = np.full(n, np.nan); lok[:-k] = lo[k:]
        first_t = np.where(np.isinf(first_t) & (hik >= tgt), k, first_t)
        first_s = np.where(np.isinf(first_s) & (lok <= stp), k, first_s)
    y = (first_t < first_s).astype(float)
    y[np.isnan(atr)] = np.nan
    y[n - h:] = np.nan
    return pd.Series(y, index=df.index)


def prod_label(df: pd.DataFrame, h: int, gain: float) -> pd.Series:
    c = df["close"]
    y = (c.shift(-h) / c - 1 >= gain).astype(float)
    y.iloc[-h:] = np.nan
    return y


def hist_rate(y: pd.Series, h: int) -> pd.Series:
    known = y.shift(h)
    return known.expanding(min_periods=100).mean()


def build_panel(raw: pd.DataFrame) -> pd.DataFrame:
    spy = raw.xs("SPY", axis=1, level=1).rename(columns=str.lower).dropna(subset=["close"])
    spy_c = spy["close"]
    spy_feat = pd.DataFrame({
        "spy_ret20": spy_c.pct_change(20),
        "spy_ret60": spy_c.pct_change(60),
        "spy_above_ma200": (spy_c > spy_c.rolling(200).mean()).astype(int),
        "spy_vol20": spy_c.pct_change().rolling(20).std() * np.sqrt(252),
        "spy_dd_1y": 1 - spy_c / spy_c.rolling(252, min_periods=60).max(),
    })
    frames = []
    tickers = [t for t in raw.columns.get_level_values(1).unique() if t != "SPY"]
    for i, t in enumerate(tickers):
        df = raw.xs(t, axis=1, level=1).rename(columns=str.lower).dropna(subset=["close", "high", "low"])
        if len(df) < 600:
            continue
        f = build_features(df, t, "short")
        if f is None:
            continue
        f = f.drop(columns=["target", "regime_label"], errors="ignore")
        f["atr_pct"] = _atr_pct(df)
        f = f.join(spy_feat, how="left")
        f["rs20"] = f["price_ret_20d"] - f["spy_ret20"]
        f["rs60"] = f["price_ret_60d"] - f["spy_ret60"]
        for h in (20, 60):
            yp = prod_label(df, h, get_target_gain(t, "short" if h == 20 else "medium"))
            ys = plan_label(df, h, *PLAN[h])
            f[f"y_prod{h}"], f[f"hist_prod{h}"] = yp, hist_rate(yp, h)
            f[f"y_plan{h}"], f[f"hist_plan{h}"] = ys, hist_rate(ys, h)
        f = f.iloc[260::STEP]
        f["ticker"] = t
        frames.append(f)
        if i % 100 == 0:
            print("panel", i, t, flush=True)
    p = pd.concat(frames)
    p.index.name = "date"
    return p.reset_index()


def _auc(y, p):
    from sklearn.metrics import roc_auc_score
    return float(roc_auc_score(y, p)) if len(set(y)) > 1 else None


def evaluate(panel: pd.DataFrame, label: str, h: int) -> dict:
    import lightgbm as lgb
    from sklearn.isotonic import IsotonicRegression

    ycol, hcol = f"y_{label}{h}", f"hist_{label}{h}"
    feats = [c for c in panel.columns if c not in ("date", "ticker") and not c.startswith(("y_", "hist_"))]
    d = panel.dropna(subset=[ycol]).copy()
    d["year"] = d["date"].dt.year
    oos, prev = [], None
    for y in TEST_YEARS:
        cutoff = pd.Timestamp(f"{y}-01-01") - pd.tseries.offsets.BDay(h + 5)
        tr, te = d[d["date"] < cutoff], d[d["year"] == y].copy()
        if len(tr) < 20000 or te.empty:
            continue
        m = lgb.LGBMClassifier(n_estimators=300, learning_rate=0.03, num_leaves=15, min_child_samples=500,
                               subsample=0.7, subsample_freq=1, colsample_bytree=0.8, reg_lambda=5.0, verbose=-1)
        m.fit(tr[feats], tr[ycol])
        te["p_raw"] = m.predict_proba(te[feats])[:, 1]
        te["base"] = tr[ycol].mean()
        te["hist"] = te[hcol].fillna(te["base"])
        if prev is not None:
            iso = IsotonicRegression(out_of_bounds="clip", y_min=0.01, y_max=0.99).fit(prev["p_raw"], prev[ycol])
            te["p_cal"] = iso.predict(te["p_raw"])
        else:
            te["p_cal"] = np.nan
        prev = te
        oos.append(te)
        print(label, h, y, "auc", round(_auc(te[ycol], te["p_raw"]) or 0, 3), flush=True)
    o = pd.concat(oos).dropna(subset=["p_cal"])
    o["p_blend"] = 0.5 * o["p_cal"] + 0.5 * o["hist"]
    y = o[ycol].to_numpy()
    out = {"n": int(len(o)), "base_rate": round(float(y.mean()), 4), "years": sorted(o["year"].unique().tolist())}
    briers = {}
    for k in ("base", "hist", "p_raw", "p_cal", "p_blend"):
        briers[k] = float(np.mean((o[k].to_numpy() - y) ** 2))
        out[k] = {"brier": round(briers[k], 5), "auc": None if k == "base" else round(_auc(y, o[k]) or 0, 4)}
    for k in ("p_raw", "p_cal", "p_blend"):
        out[k]["skill_vs_hist_pct"] = round(100 * (1 - briers[k] / briers["hist"]), 2)
        out[k]["skill_vs_base_pct"] = round(100 * (1 - briers[k] / briers["base"]), 2)
    out["hist"]["skill_vs_base_pct"] = round(100 * (1 - briers["hist"] / briers["base"]), 2)
    o["dec"] = o.groupby("date")["p_cal"].rank(pct=True)
    out["top_decile_hit"] = round(float(o.loc[o["dec"] >= 0.9, ycol].mean()), 4)
    out["bottom_decile_hit"] = round(float(o.loc[o["dec"] <= 0.1, ycol].mean()), 4)
    out["per_year_auc"] = {int(yr): round(_auc(g[ycol], g["p_raw"]) or 0, 3) for yr, g in o.groupby("year")}
    bins = [0, .2, .4, .6, .8, 1.01]
    o["b"] = pd.cut(o["p_cal"], bins, right=False)
    out["calibration"] = [{"bucket": str(b), "pred": round(float(g["p_cal"].mean()), 3),
                           "actual": round(float(g[ycol].mean()), 3), "n": int(len(g))}
                          for b, g in o.groupby("b", observed=True)]
    imp = pd.Series(m.booster_.feature_importance("gain"), index=feats).sort_values(ascending=False)
    out["top_features"] = [[k, round(float(v / imp.sum()), 3)] for k, v in imp.head(10).items()]
    return out


def main() -> None:
    src = sys.argv[1] if len(sys.argv) > 1 else "/home/ubuntu/sbt_full/ohlcv.pkl"
    dst = Path(sys.argv[2] if len(sys.argv) > 2 else "/home/ubuntu/model_exp/result.json")
    cache = dst.with_name("panel.pkl")
    if cache.exists():
        panel = pd.read_pickle(cache)
    else:
        panel = build_panel(pd.read_pickle(src))
        panel.to_pickle(cache)
    print("panel rows", len(panel), flush=True)
    res = {f"{lab}{h}": evaluate(panel, lab, h) for lab in ("prod", "plan") for h in (20, 60)}
    dst.write_text(json.dumps(res, indent=1, default=str))
    print(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    main()
