"""
Quantify how often the HMM bear gate (>80% bear) fires and its effective multiplier stack.

Run from repo root or backend/:
  python scripts/audit_hmm_bear_penalty.py
  python scripts/audit_hmm_bear_penalty.py --tickers GLD,SLV,AAPL

Uses run_confidence() — needs network for prices. Reads penalty_audit from the engine output.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config_loader import load_config  # noqa: E402
from signals.confidence_engine import run_confidence  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser(description="Audit HMM bear penalty frequency and multipliers")
    p.add_argument(
        "--tickers",
        type=str,
        default="",
        help="Comma-separated symbols (default: watchlist from config)",
    )
    args = p.parse_args()
    config = load_config()
    if args.tickers.strip():
        tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    else:
        tickers = list(config.get("watchlist") or [])
    if not tickers:
        print("No tickers: set --tickers or config watchlist")
        sys.exit(1)

    rows: list[dict] = []
    n_trig = 0
    n_soft = 0
    n_hard = 0

    for sym in tickers:
        try:
            out = run_confidence(sym, period="2y", market_regime="NEUTRAL", config=config)
        except Exception as e:
            rows.append({"ticker": sym, "error": str(e)})
            continue
        pa = out.get("penalty_audit") or {}
        hb = pa.get("hmm_bear_penalty") or {}
        trig = bool(hb.get("triggered"))
        if trig:
            n_trig += 1
            if hb.get("variant") == "soft_above_ma200":
                n_soft += 1
            elif hb.get("variant") == "hard":
                n_hard += 1
        rows.append(
            {
                "ticker": sym,
                "confidence_final": pa.get("confidence_final"),
                "confidence_blend_only": pa.get("confidence_blend_only"),
                "bear_prob_pct": round(hb.get("bear_probability") * 100, 1)
                if hb.get("bear_probability") is not None
                else None,
                "hmm_penalty_triggered": trig,
                "hmm_variant": hb.get("variant"),
                "hmm_mult": hb.get("multiplier"),
                "combined_mult": pa.get("combined_multiplier"),
            }
        )

    n = len([r for r in rows if "error" not in r])
    print(f"Sample: {n} tickers | HMM bear gate triggered: {n_trig} ({100 * n_trig / max(n, 1):.1f}%)")
    if n_trig:
        print(f"  Of those: soft (above MA200)={n_soft}, hard={n_hard}")
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
