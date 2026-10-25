"""
Backtest the core/satellite regime rule on SPY since 1993 (T-bill yield from ^IRX for cash),
over the full history and three sub-periods, for a small grid of risk-off exposures and bands.

    python scripts/regime_allocation_backtest.py
Writes data/alpha/regime_allocation_backtest.json.
"""
from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore")

from signals.alpha.core_satellite import DEFAULTS, _metrics, backtest  # noqa: E402

PERIODS = [("1994", "2007"), ("2008", "2016"), ("2017", "2026")]


def _hist(sym: str) -> pd.Series:
    import yfinance as yf

    h = yf.Ticker(sym).history(period="max", auto_adjust=True)["Close"]
    h.index = pd.DatetimeIndex(h.index).tz_localize(None).normalize()
    return h


def main() -> None:
    spy, irx = _hist("SPY"), _hist("^IRX")
    grid = []
    for off in (0, 30, 50):
        for band in (0.0, 1.0, 2.0):
            cfg = {**DEFAULTS, "risk_off_equity_pct": off, "band_pct": band}
            bt = backtest(spy, irx, cfg=cfg)
            row = {
                "risk_off_equity_pct": off, "band_pct": band,
                "full": {"buy_hold": bt["buy_hold"], "regime": bt["regime"]},
                "avg_equity_pct": bt["avg_equity_pct"], "switches_per_year": bt["switches_per_year"],
            }
            for a, b in PERIODS:
                s, r = bt["equity_curve"].loc[a:b], bt["bh_curve"].loc[a:b]
                row[f"{a}-{b}"] = {"buy_hold": _metrics(r), "regime": _metrics(s)}
            grid.append(row)
            f = row["full"]
            print(f"off={off:>2}% band={band}%  regime CAGR {f['regime']['cagr_pct']:5.2f} Sharpe {f['regime']['sharpe']:.2f} "
                  f"DD {f['regime']['max_dd_pct']:6.2f} | B&H CAGR {f['buy_hold']['cagr_pct']:5.2f} Sharpe {f['buy_hold']['sharpe']:.2f} "
                  f"DD {f['buy_hold']['max_dd_pct']:6.2f} | sw/yr {row['switches_per_year']}  "
                  + "  ".join(f"{a}-{b}: S {row[f'{a}-{b}']['regime']['sharpe']:.2f} vs {row[f'{a}-{b}']['buy_hold']['sharpe']:.2f}" for a, b in PERIODS))
    out = ROOT / "data" / "alpha" / "regime_allocation_backtest.json"
    out.write_text(json.dumps({"defaults": DEFAULTS, "grid": grid}, indent=2))
    print("->", out)


if __name__ == "__main__":
    main()
