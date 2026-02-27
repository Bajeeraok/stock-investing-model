"""
ML model pre-trainer for Thrive Alpha.

Run this ONCE initially (takes ~30 min for a 30-ticker watchlist),
then it runs automatically as part of run_daily.py on a weekly schedule.

What it does per ticker:
  1. Download historical OHLCV (period configured per ticker in config.yaml)
  2. Build feature matrix (13 technical features, all backward-looking)
  3. Label each bar: did price rise 10%+ in next 20 trading days? (0/1)
  4. Chronological 80/20 train/test split (no random shuffling = no leakage)
  5. Fit LightGBM, evaluate AUC + Brier score on held-out test set
  6. Fit HMM on daily returns + volatility (2y history)
  7. Save both models to data/models/{lgbm,hmm}_{TICKER}.pkl

Daily run behaviour (after initial training):
  - Models are LOADED from disk, not retrained (milliseconds per ticker)
  - Retrain fires automatically when model file age > retrain_interval_days (default: 7)
  - predict_probability() calls model.predict_proba([today_features]) → 1 number

Usage:
    python scripts/train_ml_models.py                 # train all watchlist tickers
    python scripts/train_ml_models.py --ticker NVDA   # train single ticker
    python scripts/train_ml_models.py --force         # force retrain even if fresh
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import yaml
from signals.fetcher import fetch_ohlcv_dataframe, fetch_ohlcv_safe
from signals.ml_models import get_lgbm_period, model_needs_retrain, train_and_save
from signals.hmm_regime import get_hmm_regime, MIN_BARS_TO_FIT


def _load_config() -> dict:
    path = ROOT / "config" / "config.yaml"
    if path.exists():
        with open(path) as f:
            return yaml.safe_load(f) or {}
    return {}


def train_ticker(ticker: str, config: dict, force: bool = False) -> dict:
    """Train LightGBM + HMM for one ticker. Returns result summary."""
    ml_cfg  = config.get("ml_models", {})
    enabled = ml_cfg.get("enabled", True)

    result: dict = {"ticker": ticker, "lgbm": {}, "hmm": {}}

    # ── LightGBM ────────────────────────────────────────────────────────────
    if not enabled:
        result["lgbm"] = {"skipped": "ml_models.enabled is false in config"}
    elif not force and not model_needs_retrain(ticker, config):
        result["lgbm"] = {"skipped": "model fresh (< retrain_interval_days old)"}
    else:
        period = get_lgbm_period(ticker, config)
        print(f"  LGBM: fetching {period} OHLCV for {ticker}...", end=" ", flush=True)
        t0 = time.time()
        df = fetch_ohlcv_dataframe(ticker, period)
        if df is None or len(df) < 400:
            result["lgbm"] = {"error": f"Insufficient data ({len(df) if df is not None else 0} bars for {period})"}
            print(f"FAIL — {result['lgbm']['error']}")
        else:
            print(f"{len(df)} bars → training...", end=" ", flush=True)
            metrics = train_and_save(ticker, df)
            elapsed = round(time.time() - t0, 1)
            if "error" in metrics:
                result["lgbm"] = metrics
                print(f"FAIL — {metrics['error']}")
            else:
                result["lgbm"] = {**metrics, "period": period, "elapsed_s": elapsed}
                auc   = metrics.get("auc", "?")
                base  = metrics.get("base_rate", "?")
                feats = metrics.get("top_features", [])[:3]
                print(f"OK  AUC={auc}  base_rate={base}  ({elapsed}s)")

                # Regime coverage: critical diagnostic
                cov = metrics.get("regime_coverage", {})
                if cov:
                    cov_str = "  ".join(f"{r}={cov.get(r,0):.0f}%" for r in ["BULL","TRANSITION","BEAR","HIGH_VOL"])
                    print(f"    Regime coverage: {cov_str}")
                for w in metrics.get("regime_warnings", []):
                    print(f"    ⚠ {w}")

                # Regime-stratified AUC: did it learn all market environments?
                abr = metrics.get("auc_by_regime", {})
                if abr:
                    abr_str = "  ".join(f"{r}={v}" for r, v in abr.items())
                    print(f"    AUC by regime:   {abr_str}")

    # ── HMM ─────────────────────────────────────────────────────────────────
    hmm_period = ml_cfg.get("hmm_period", "2y")
    print(f"  HMM:  fetching {hmm_period} OHLCV for {ticker}...", end=" ", flush=True)
    t0 = time.time()
    close = fetch_ohlcv_safe(ticker, hmm_period)
    if close is None or len(close) < MIN_BARS_TO_FIT:
        result["hmm"] = {"error": f"Need {MIN_BARS_TO_FIT}+ bars; got {len(close) if close is not None else 0}"}
        print(f"FAIL — {result['hmm']['error']}")
    else:
        hmm_out = get_hmm_regime(ticker, close, force_refit=force)
        elapsed = round(time.time() - t0, 1)
        if hmm_out and not hmm_out.get("error"):
            result["hmm"] = {
                "bars": hmm_out["n_bars_fit"],
                "dominant_state": hmm_out["dominant_state"],
                "bull_prob": hmm_out["bull_probability"],
                "period": hmm_period,
                "elapsed_s": elapsed,
            }
            print(
                f"OK  dominant={hmm_out['dominant_state']}  "
                f"bull={hmm_out['bull_probability']*100:.0f}%  ({elapsed}s)"
            )
        else:
            err = (hmm_out or {}).get("error", "unknown error")
            result["hmm"] = {"error": err}
            print(f"FAIL — {err}")

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Pre-train ML models for Thrive Alpha watchlist")
    parser.add_argument("--ticker", type=str, default=None,
                        help="Train single ticker (default: all watchlist tickers)")
    parser.add_argument("--force", action="store_true",
                        help="Force retrain even if model is fresh")
    args = parser.parse_args()

    config   = _load_config()
    watchlist = config.get("watchlist", [])

    if args.ticker:
        tickers = [args.ticker.upper()]
    else:
        tickers = [t.upper() for t in watchlist]

    if not tickers:
        print("No tickers found. Add tickers to watchlist in config.yaml.")
        return

    print(f"\nThrive Alpha — ML Model Trainer")
    print(f"Tickers: {len(tickers)}  |  Force retrain: {args.force}")
    retrain_days = config.get("ml_models", {}).get("retrain_interval_days", 7)
    print(f"Retrain schedule: every {retrain_days} days (model file age check)")
    print("=" * 70)

    results = []
    t_start = time.time()

    for i, ticker in enumerate(tickers, 1):
        print(f"\n[{i}/{len(tickers)}] {ticker}")
        r = train_ticker(ticker, config, force=args.force)
        results.append(r)

    total = round(time.time() - t_start, 1)
    print(f"\n{'='*70}")
    print(f"Completed {len(tickers)} tickers in {total}s")
    print("\nSummary:")

    lgbm_ok   = sum(1 for r in results if "auc" in r["lgbm"])
    lgbm_skip = sum(1 for r in results if "skipped" in r["lgbm"])
    lgbm_fail = sum(1 for r in results if "error" in r["lgbm"])
    hmm_ok    = sum(1 for r in results if "dominant_state" in r["hmm"])
    hmm_fail  = sum(1 for r in results if "error" in r["hmm"])

    print(f"  LightGBM: {lgbm_ok} trained  {lgbm_skip} skipped (fresh)  {lgbm_fail} failed")
    print(f"  HMM:      {hmm_ok} trained  {hmm_fail} failed")

    if lgbm_ok:
        aucs = [r["lgbm"]["auc"] for r in results if "auc" in r["lgbm"]]
        print(f"  LGBM AUC range: {min(aucs):.3f} – {max(aucs):.3f}")
        if any(a < 0.55 for a in aucs):
            poor = [r["ticker"] for r in results if r["lgbm"].get("auc", 1) < 0.55]
            print(f"  ! AUC < 0.55 for: {poor} — weak ML signal, rely on rule-based for these")

    print(f"\nModels saved to: {ROOT / 'data' / 'models'}")
    print("Daily runs will LOAD models (fast) and only RETRAIN when model age exceeds retrain_interval_days.")


if __name__ == "__main__":
    main()
