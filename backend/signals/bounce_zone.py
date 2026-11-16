"""
Bounce zone for dip stocks: where the low of the next ~40 sessions usually lands, sized by the
stock's own 20-day EWMA volatility. Context only — never a reason to wait, never feeds a signal.

Trigger: close ≥15% below its 252-day high and below its 50-day average.
Fit on 2015–2020 (19,923 events), tested 2021–2026 (48,902 events, 124 tickers):
  • 80% zone caught the actual 40-day low 84.8% of the time (81–87% every year), width ~31% of price.
  • Median error of the predicted bottom 7.2% vs 11.3% for "bottom is today".
  • Limit buy at the median bottom filled 58%: +7.5% at 60 days vs +7.7% buying now;
    the 42% that never filled returned +23.1%.
Write-up: docs/research/findings/2026-11-16-bounce-zone.md
"""
from __future__ import annotations

import math
from typing import Any

from signals.stock_day_range import ewma_sigmas

HORIZON = 40
DD_TRIGGER = -0.15
# Further fall to the 40-day low in daily σ20 units: (10th, 50th, 90th percentile), by drawdown bucket.
QUANTILES = (
    (-0.40, (-11.85, -3.32, -0.26)),
    (-0.25, (-11.21, -2.69, -0.27)),
    (-0.15, (-11.60, -3.41, -0.36)),
)
TEST = {"from": "2021", "events": 48902, "tickers": 124, "coverage_pct": 84.8, "median_err_pct": 7.2,
        "limit_fill_pct": 58, "ret_limit_pct": 7.5, "ret_now_pct": 7.7, "ret_missed_pct": 23.1}


def bounce_zone(closes: list[float]) -> dict[str, Any] | None:
    """closes: completed daily closes, oldest first. None unless the stock is in a dip."""
    if len(closes) < 200:
        return None
    c = closes[-1]
    hi = max(closes[-252:])
    ma50 = sum(closes[-50:]) / 50
    sig = ewma_sigmas(closes)[-1]
    if not sig or c <= 0 or hi <= 0:
        return None
    dd = c / hi - 1
    if dd > DD_TRIGGER or c >= ma50:
        return None
    q = next(qs for edge, qs in QUANTILES if dd <= edge)
    lo, mid, top = (round(c * math.exp(k * sig), 2) for k in q)
    return {"ref_close": round(c, 2), "drawdown_pct": round(dd * 100, 1), "ma50": round(ma50, 2),
            "low": lo, "mid": mid, "high": top, "horizon_days": HORIZON, "test": TEST}
