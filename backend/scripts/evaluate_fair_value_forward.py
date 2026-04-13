"""
Evaluate fair value vs realized ~12-month forward price (historical prices only).

**Limitation (read this):** Fundamentals (PE, growth, analyst target) are taken from **today's**
yfinance snapshot for every past date. That is **not** point-in-time — results are useful to:
  - Compare **raw model** vs **capped** guardrails (use config or --no-guardrails)
  - See sensitivity of the valuation stack to the **price path**
  - Motivate building a PIT fundamentals store for real forecast accuracy

For production forecast QA, prefer: disable retail caps in ``fair_value.guardrails``, store monthly
``{ticker, date, fv, inputs_hash}``, then score vs price 12m later with **matching** inputs.

Usage (from ``backend/``):
  python scripts/evaluate_fair_value_forward.py --tickers AAPL MSFT --step 21
  python scripts/evaluate_fair_value_forward.py --tickers NVDA --no-guardrails
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _yf_fundamentals(ticker: str) -> dict:
    import yfinance as yf

    t = yf.Ticker(ticker)
    info = getattr(t, "info", None) or {}
    return info


def _fv_for_price(
    ticker: str,
    price: float,
    info: dict,
    guardrails: dict | None,
) -> tuple[float | None, str]:
    from signals.fair_value_estimator import estimate_fair_value

    ttm_pe = None
    if price and info.get("trailingEps"):
        try:
            te = float(info["trailingEps"])
            if te > 0:
                ttm_pe = round(price / te, 2)
        except (TypeError, ValueError):
            pass
    if ttm_pe is None:
        ttp = info.get("trailingPE")
        if ttp is not None:
            try:
                ttm_pe = float(ttp)
            except (TypeError, ValueError):
                pass
    if ttm_pe is None or ttm_pe <= 0:
        return None, "no_ttm_pe"

    def _pct(x):
        if x is None:
            return 10.0
        try:
            v = float(x)
            if 0 < v < 1:
                v *= 100
            return v
        except (TypeError, ValueError):
            return 10.0

    rev = _pct(info.get("revenueGrowth"))
    ear = _pct(info.get("earningsGrowth"))
    margin = info.get("profitMargins")
    if margin is not None and float(margin) < 1:
        margin = float(margin) * 100
    else:
        margin = float(margin or 15) if margin is not None else 15.0
    de = float(info.get("debtToEquity") or 0.5)
    forward_pe = info.get("forwardPE")
    try:
        forward_pe = float(forward_pe) if forward_pe is not None else None
    except (TypeError, ValueError):
        forward_pe = None
    at = info.get("targetMeanPrice")
    try:
        analyst_target = float(at) if at is not None else None
    except (TypeError, ValueError):
        analyst_target = None
    fcf = info.get("freeCashflow")
    shares = info.get("sharesOutstanding")
    try:
        fcf_f = float(fcf) if fcf is not None else None
        sh = float(shares) if shares is not None else None
        fcf_ps = (fcf_f / sh) if (fcf_f and sh and sh > 0) else None
    except (TypeError, ValueError):
        fcf_ps = None

    r = estimate_fair_value(
        current_price=price,
        ttm_pe=ttm_pe,
        sector_pe=28.0,
        revenue_growth_pct=rev,
        earnings_growth_pct=ear if ear is not None else rev,
        net_margin_pct=margin,
        de_ratio=de,
        forward_pe=forward_pe,
        sector_forward_pe=25.0,
        fcf_per_share=fcf_ps,
        analyst_target=analyst_target,
        guardrails=guardrails,
    )
    return r.fair_value, r.method_used


def main() -> int:
    parser = argparse.ArgumentParser(description="FV vs ~12m forward price (stale fundamentals caveat).")
    parser.add_argument("--tickers", nargs="+", required=True)
    parser.add_argument("--horizon", type=int, default=252, help="Forward trading days (default 252).")
    parser.add_argument("--step", type=int, default=21, help="Trading days between samples (default ~1 month).")
    parser.add_argument("--no-guardrails", action="store_true", help="Raw model (no analyst/spot caps).")
    args = parser.parse_args()

    import pandas as pd
    import yfinance as yf

    horizon = max(20, args.horizon)
    step = max(1, args.step)
    gr = (
        {"analyst_mean_cap_enabled": False, "max_implied_upside_vs_spot": None}
        if args.no_guardrails
        else None
    )

    print(
        "NOTE: Fundamentals are today's yfinance snapshot — not point-in-time. "
        "Interpret as methodology + guardrail sensitivity, not definitive MAPE.\n"
    )

    for sym in args.tickers:
        sym = sym.upper().split("-")[0]
        info = _yf_fundamentals(sym)
        hist = yf.Ticker(sym).history(period="5y", auto_adjust=True)
        if hist is None or hist.empty or "Close" not in hist.columns:
            print(f"{sym}: no history\n")
            continue
        closes = hist["Close"].dropna()
        errs: list[float] = []
        dirs_hit = 0
        dirs_tot = 0
        for i in range(0, len(closes) - horizon, step):
            p0 = float(closes.iloc[i])
            p1 = float(closes.iloc[i + horizon])
            fv, _m = _fv_for_price(sym, p0, info, gr)
            if fv is None or fv <= 0 or p1 <= 0:
                continue
            # Error: realized vs predicted level (both in price space)
            err_pct = 100.0 * (p1 - fv) / fv
            errs.append(abs(err_pct))
            # Directional: model says undervalued if fv > p0
            undervalued = fv > p0
            realized_up = p1 > p0
            if undervalued == realized_up:
                dirs_hit += 1
            dirs_tot += 1

        sym_out = {
            "ticker": sym,
            "samples": len(errs),
            "mape_pct": round(sum(errs) / len(errs), 2) if errs else None,
            "directional_accuracy": round(dirs_hit / dirs_tot, 3) if dirs_tot else None,
            "guardrails": "off" if args.no_guardrails else "config/default",
        }
        print(json.dumps(sym_out, indent=2))
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
