"""
Retrain the short-horizon ML probability on the model's own signal outcomes.

Why: the 148-snapshot audit showed the raw 0-49% LGBM prob calibrates to a flat
~51.5% base rate — the per-ticker OHLCV features carry little 21d discrimination
*at signal time*. The features that DID discriminate in the audit were the
signal's own context: dip-zone flag, gate state at signal, entry-band distance,
composite-score bucket, and their interactions with the raw prob.

This script joins each (ticker, snapshot_date) row's gate_detail_json + band /
score fields with the same 21d forward-return outcome used for calibration
(generate_validation_dataset.py), trains a gradient-boosted classifier on the
enriched feature set, and reports holdout AUC/Brier vs the raw prob baseline.

Usage:
    cd backend && python scripts/retrain_ml_on_outcomes.py
    cd backend && python scripts/retrain_ml_on_outcomes.py --forward-days 21 --dry-run

Artifacts:
    data/models/lgbm_own_outcomes_short.pkl      — trained model + feature list
    data/calibration/own_outcomes_report.json    — metrics + feature importance

lightgbm is used when installed (prod); sklearn's HistGradientBoostingClassifier
is the local fallback — identical interface, no extra deps.
"""
from __future__ import annotations

import argparse
import json
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.generate_validation_dataset import (
    _closes_by_ticker,
    _extract_ml_prob_from_gate,
    _forward_return,
    _load_snapshots,
)

MODEL_OUT = ROOT / "data" / "models" / "lgbm_own_outcomes_short.pkl"
REPORT_OUT = ROOT / "data" / "calibration" / "own_outcomes_report.json"

TRAIN_SPLIT_RATIO = 0.80  # chronological (by date) — never random shuffle

_ENTRY_MODES = ("hard_lock", "starter_only", "full_go")


def _gate_states(gate_detail_json) -> dict[str, int | None]:
    """Parse per-gate pass flags out of a snapshot row's gate_detail_json."""
    out = {f"gate_{g}_pass": None for g in ("valuation", "regime", "momentum", "ml")}
    out["gates_passed_n"] = None
    if not gate_detail_json:
        return out
    try:
        gates = json.loads(gate_detail_json) if isinstance(gate_detail_json, str) else gate_detail_json
    except Exception:
        return out
    if not isinstance(gates, list):
        return out
    n_pass = 0
    for g in gates:
        if not isinstance(g, dict):
            continue
        gid = g.get("id")
        if gid in ("valuation", "regime", "momentum", "ml"):
            p = g.get("pass")
            out[f"gate_{gid}_pass"] = None if p is None else int(bool(p))
        if g.get("pass"):
            n_pass += 1
    out["gates_passed_n"] = n_pass
    return out


def _band_feats(row: dict) -> dict[str, float | int | None]:
    close = row.get("close")
    band = row.get("st_band") or {}
    try:
        cp = float(close) if close is not None else None
    except (TypeError, ValueError):
        cp = None
    lo, hi = band.get("low"), band.get("high")
    try:
        lo = float(lo) if lo is not None else None
        hi = float(hi) if hi is not None else None
    except (TypeError, ValueError):
        lo = hi = None
    if cp is None or cp <= 0 or lo is None or hi is None or hi <= lo:
        return {"inside_st_band": None, "band_dist_pct": None, "band_width_pct": None}
    mid = (lo + hi) / 2.0
    return {
        "inside_st_band": int(lo <= cp <= hi),
        "band_dist_pct": round(100.0 * (cp - mid) / mid, 3),
        "band_width_pct": round(100.0 * (hi - lo) / mid, 3),
    }


def build_dataset(snapshots: dict[str, dict], forward_days: int, benchmark: str = "SPY") -> pd.DataFrame:
    """One row per (ticker, date) with signal-context features + outcome.

    `bench_fwd` is the benchmark's own forward return over the same window —
    absolute labels use y = fwd>0; excess labels (the honest 'beat the index'
    objective) use y = fwd > bench_fwd.
    """
    dates_sorted = sorted(snapshots.keys())
    closes = _closes_by_ticker(snapshots)
    bench = closes.get(benchmark.upper(), {})
    records: list[dict] = []

    for i, date in enumerate(dates_sorted):
        later = dates_sorted[i + 1:]
        bench_fwd = _forward_return(bench, date, later, forward_days) if bench else None
        for row in snapshots[date].get("run_results") or []:
            if not isinstance(row, dict):
                continue
            t = row.get("ticker")
            if not t:
                continue
            prob = _extract_ml_prob_from_gate(row)
            if prob is None:
                continue
            t_later = [d for d in later if d in closes.get(t, {})]
            fwd = _forward_return(closes[t], date, t_later, forward_days)
            if fwd is None:
                continue
            if bench_fwd is None:
                y_val = int(fwd > 0)
                excess = None
            else:
                excess = fwd - bench_fwd
                y_val = int(fwd > 0)  # absolute default; caller may flip to excess

            score = row.get("composite_buy")
            try:
                score = float(score) if score is not None else None
            except (TypeError, ValueError):
                score = None
            entry_mode = str(row.get("entry_mode") or "").strip() or None
            dip_zone = bool(
                score is not None
                and 30 <= score < 50
                and entry_mode in ("starter_only", "full_go")
            )

            rec: dict = {
                "date": date,
                "ticker": t,
                "ml_prob": prob / 100.0,
                "score": score,
                "dip_zone": int(dip_zone),
                "inside_st_band": None,
                "band_dist_pct": None,
                "band_width_pct": None,
                "entry_mode": entry_mode,
                "regime": str(row.get("regime") or "unknown").lower(),
                "y": y_val,
                "excess_ret": excess,
            }
            rec.update(_band_feats(row))
            rec.update(_gate_states(row.get("gate_detail_json")))
            rec["gate_cleared"] = int(bool(row.get("gate_cleared")))

            for src, dst in (
                ("rsi", "rsi"), ("trend_score", "trend_score"),
                ("readiness_score", "readiness_score"), ("velocity_score", "velocity_score"),
                ("swing_score", "swing_score"), ("rvol", "rvol"), ("bb_pct_b", "bb_pct_b"),
            ):
                v = row.get(src)
                try:
                    rec[dst] = float(v) if v is not None else None
                except (TypeError, ValueError):
                    rec[dst] = None

            close = row.get("close")
            ma50 = row.get("ma50")
            h52, l52 = row.get("high_52w"), row.get("low_52w")
            try:
                cp = float(close) if close is not None else None
                rec["above_ma50"] = int(cp > float(ma50)) if cp and ma50 else None
                rec["dist_52w_high_pct"] = round(100.0 * (float(h52) - cp) / cp, 2) if cp and h52 else None
                rec["dist_52w_low_pct"] = round(100.0 * (cp - float(l52)) / cp, 2) if cp and l52 else None
            except (TypeError, ValueError):
                rec["above_ma50"] = rec["dist_52w_high_pct"] = rec["dist_52w_low_pct"] = None

            records.append(rec)

    df = pd.DataFrame.from_records(records)
    if df.empty:
        return df

    # Score bucket one-hots + interactions the audit flagged.
    s = df["score"].fillna(50.0)
    df["score_30_50"] = ((s >= 30) & (s < 50)).astype(int)
    df["score_50_70"] = ((s >= 50) & (s < 70)).astype(int)
    df["score_70_100"] = (s >= 70).astype(int)
    df["score_norm"] = s / 100.0
    df["ml_x_dip"] = df["ml_prob"] * df["dip_zone"]
    df["ml_x_score70"] = df["ml_prob"] * df["score_70_100"]
    df["ml_x_in_band"] = df["ml_prob"] * df["inside_st_band"].fillna(0)

    # Categorical one-hots (entry_mode, regime).
    df["entry_mode"] = df["entry_mode"].fillna("hard_lock")
    df = pd.get_dummies(
        df,
        columns=["entry_mode", "regime"],
        prefix=["entry", "regime"],
        dummy_na=False,
    )
    for m in _ENTRY_MODES:
        col = f"entry_{m}"
        if col not in df.columns:
            df[col] = 0
    return df


_FEATURE_COLS = [
    "ml_prob", "score_norm",
    "score_30_50", "score_50_70", "score_70_100",
    "dip_zone", "inside_st_band", "band_dist_pct", "band_width_pct",
    "gate_valuation_pass", "gate_regime_pass", "gate_momentum_pass", "gate_ml_pass",
    "gates_passed_n", "gate_cleared",
    "rsi", "trend_score", "readiness_score", "velocity_score", "swing_score",
    "rvol", "bb_pct_b", "above_ma50", "dist_52w_high_pct", "dist_52w_low_pct",
    "ml_x_dip", "ml_x_score70", "ml_x_in_band",
    "entry_hard_lock", "entry_starter_only", "entry_full_go",
]


def _make_model():
    try:
        import lightgbm as lgb

        return lgb.LGBMClassifier(
            n_estimators=400, learning_rate=0.03, num_leaves=15,
            feature_fraction=0.8, bagging_fraction=0.8, bagging_freq=5,
            min_child_samples=40, random_state=42, verbose=-1,
        ), "lightgbm"
    except (ImportError, OSError):
        from sklearn.ensemble import HistGradientBoostingClassifier

        return HistGradientBoostingClassifier(
            max_iter=400, learning_rate=0.03, max_leaf_nodes=15,
            min_samples_leaf=40, random_state=42,
        ), "hist_gradient_boosting"


def main() -> None:
    ap = argparse.ArgumentParser(description="Retrain short ML on own signal outcomes")
    ap.add_argument("--eod-dir", type=str, default="data/eod")
    ap.add_argument("--forward-days", type=int, default=21)
    ap.add_argument("--label", type=str, default="absolute", choices=["absolute", "excess"],
                    help="absolute: y=1 if fwd>0 · excess: y=1 if fwd beats SPY over same window")
    ap.add_argument("--benchmark", type=str, default="SPY")
    ap.add_argument("--dry-run", action="store_true", help="report metrics only — don't save artifacts")
    args = ap.parse_args()

    eod_dir = Path(args.eod_dir)
    if not eod_dir.is_absolute():
        eod_dir = ROOT / eod_dir
    snapshots = _load_snapshots(eod_dir)
    print(f"{len(snapshots)} snapshots")
    if len(snapshots) < 30:
        print("Need ~30+ snapshots.")
        return

    df = build_dataset(snapshots, args.forward_days, args.benchmark)
    if df.empty:
        print("No feature rows.")
        return
    if args.label == "excess":
        df = df.dropna(subset=["excess_ret"])
        df["y"] = (df["excess_ret"] > 0).astype(int)
    print(f"dataset: {len(df)} rows · base rate {df['y'].mean():.3f} · label={args.label}")

    # Dynamic feature list: fixed cols that exist + any regime_* one-hot columns.
    feature_cols = [c for c in _FEATURE_COLS if c in df.columns]
    feature_cols += sorted(c for c in df.columns if c.startswith("regime_"))
    X = df[feature_cols]
    y = df["y"]

    # Chronological split by date — snapshots are the time axis.
    unique_dates = sorted(df["date"].unique())
    split_idx = int(len(unique_dates) * TRAIN_SPLIT_RATIO)
    train_dates = set(unique_dates[:split_idx])
    tr = df["date"].isin(train_dates)
    X_tr, X_te, y_tr, y_te = X[tr], X[~tr], y[tr], y[~tr]
    print(f"train {len(X_tr)} / test {len(X_te)} · test dates {unique_dates[split_idx]}+")

    model, backend = _make_model()
    model.fit(X_tr, y_tr)

    from sklearn.metrics import brier_score_loss, roc_auc_score

    probs = model.predict_proba(X_te)[:, 1] if hasattr(model, "predict_proba") else model.decision_function(X_te)
    # Baseline: raw ml_prob on the same test rows.
    base = X_te["ml_prob"].astype(float).values

    report: dict = {
        "backend": backend,
        "n_train": int(len(X_tr)),
        "n_test": int(len(X_te)),
        "forward_days": args.forward_days,
        "base_rate": round(float(y.mean()), 4),
        "features": feature_cols,
        "test_auc_model": round(float(roc_auc_score(y_te, probs)), 4) if y_te.nunique() > 1 else None,
        "test_auc_raw_prob": round(float(roc_auc_score(y_te, base)), 4) if y_te.nunique() > 1 else None,
        "test_brier_model": round(float(brier_score_loss(y_te, probs)), 4),
        "test_brier_raw_prob": round(float(brier_score_loss(y_te, base)), 4),
    }

    if hasattr(model, "feature_importances_"):
        imp = dict(zip(feature_cols, model.feature_importances_))
        report["top_features"] = sorted(imp.items(), key=lambda kv: -kv[1])[:10]

    print(json.dumps(report, indent=2))

    if args.dry_run:
        print("--dry-run: no artifacts written")
        return

    MODEL_OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(MODEL_OUT, "wb") as f:
        pickle.dump({"model": model, "backend": backend, "features": feature_cols}, f)
    REPORT_OUT.parent.mkdir(parents=True, exist_ok=True)
    REPORT_OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nmodel -> {MODEL_OUT}")
    print(f"report -> {REPORT_OUT}")


if __name__ == "__main__":
    main()
