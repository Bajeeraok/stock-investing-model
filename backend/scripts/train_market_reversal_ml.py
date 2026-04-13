"""
Train LightGBM for P(strong bounce over next 5 sessions | features at t).

Label (stress-conditioned): y=1 if max SPY return over days t+1..t+5 >= target_pct,
only on rows where stress proxy is true (drawdown, VIX, or negative 5d return).

Usage (from backend/):
  python scripts/train_market_reversal_ml.py

Requires: pandas, numpy, lightgbm, sklearn
"""
from __future__ import annotations

import argparse
import json
import pickle
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

from signals.fetcher import fetch_ohlcv_safe
from signals.market_reversal_overlay import FEATURE_COLUMNS, feature_row_from_series

# ---------------------------------------------------------------------------
# Build historical feature matrix (same logic as live, rolling)
# ---------------------------------------------------------------------------


def _rolling_features(spy: pd.Series, vix: pd.Series) -> pd.DataFrame | None:
    common = spy.index.intersection(vix.index)
    if len(common) < 260:
        return None
    s = spy.reindex(common).ffill().bfill()
    vx = vix.reindex(common).ffill().bfill()

    rows = []
    for i in range(220, len(s)):
        ss = s.iloc[: i + 1]
        vv = vx.iloc[: i + 1]
        f = feature_row_from_series(ss, vv)
        if f:
            f["dt"] = s.index[i]
            rows.append(f)
    if not rows:
        return None
    return pd.DataFrame(rows).set_index("dt")


def _forward_max_return_5d(close: pd.Series) -> pd.Series:
    """Max close[t+k]/close[t]-1 for k=1..5."""
    out = []
    for i in range(len(close)):
        if i + 5 >= len(close):
            out.append(np.nan)
            continue
        window = close.iloc[i + 1 : i + 6]
        m = (window.max() / close.iloc[i]) - 1.0
        out.append(m)
    return pd.Series(out, index=close.index)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--period", default="15y", help="yfinance period for SPY/VIX")
    p.add_argument("--target-pct", type=float, default=0.02, help="Min forward 5d max return for positive label")
    p.add_argument(
        "--no-stress-only",
        action="store_true",
        help="Train on all days (not recommended — very imbalanced)",
    )
    p.add_argument("--out", default=None, help="Output pickle path")
    args = p.parse_args()

    spy = fetch_ohlcv_safe("SPY", args.period)
    vix = fetch_ohlcv_safe("^VIX", args.period)
    if spy is None or vix is None:
        print("Failed to fetch SPY or ^VIX")
        sys.exit(1)

    common = spy.index.intersection(vix.index)
    spy = spy.reindex(common).ffill()
    vix = vix.reindex(common).ffill()

    feat_df = _rolling_features(spy, vix)
    if feat_df is None or feat_df.empty:
        print("Could not build features")
        sys.exit(1)

    close = spy.reindex(feat_df.index).ffill()
    fwd = _forward_max_return_5d(close).reindex(feat_df.index)
    ret5 = close.pct_change(5).reindex(feat_df.index)
    vix_lvl = vix.reindex(feat_df.index).ffill()

    stress = (ret5 < -0.015) | (vix_lvl > 22) | (feat_df["spy_dd_20h"] < -0.025)
    y = (fwd >= args.target_pct).astype(int)
    valid = stress & y.notna() & fwd.notna()
    if args.stress_only:
        mask = valid
    else:
        mask = y.notna() & fwd.notna()

    sub = feat_df.loc[mask].copy()
    y_sub = y.loc[mask]
    if len(sub) < 80:
        print(f"Too few samples: {len(sub)} — widen period or relax stress filter")
        sys.exit(1)

    X = sub[FEATURE_COLUMNS].values.astype(np.float64)
    y_arr = y_sub.values.astype(int)

    # Time-ordered split
    split = int(len(X) * 0.75)
    X_train, X_test = X[:split], X[split:]
    y_train, y_test = y_arr[:split], y_arr[split:]

    try:
        import lightgbm as lgb
        from sklearn.metrics import roc_auc_score
    except ImportError as e:
        print(f"Need lightgbm + sklearn: {e}")
        sys.exit(1)

    clf = lgb.LGBMClassifier(
        n_estimators=200,
        learning_rate=0.05,
        max_depth=4,
        num_leaves=16,
        subsample=0.85,
        colsample_bytree=0.85,
        class_weight="balanced",
        random_state=42,
        verbose=-1,
    )
    clf.fit(X_train, y_train)
    try:
        auc = roc_auc_score(y_test, clf.predict_proba(X_test)[:, 1])
        print(f"Hold-out ROC-AUC (rough): {auc:.3f}  n_train={len(X_train)} n_test={len(X_test)} pos%={100*y_arr.mean():.1f}")
    except Exception as e:
        print(f"AUC skip: {e}")
        auc = None

    out_path = Path(args.out) if args.out else ROOT / "data" / "models" / "market_reversal_lgbm.pkl"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    bundle = {
        "model": clf,
        "feature_columns": FEATURE_COLUMNS,
        "meta": {
            "target_pct": args.target_pct,
            "stress_only": stress_only,
            "period": args.period,
            "roc_auc_holdout": auc,
            "n_samples": len(X),
        },
    }
    with open(out_path, "wb") as f:
        pickle.dump(bundle, f)
    print(f"Saved {out_path}")
    with open(out_path.with_suffix(".json"), "w") as jf:
        json.dump({k: v for k, v in bundle["meta"].items() if k != "model"}, jf, indent=2, default=str)


if __name__ == "__main__":
    main()
