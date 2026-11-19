# Options-implied day range vs our EWMA range
2026-11-18 · Status: passes the bar on 10 liquid tickers; not shipped (awaiting approval, display only)

**Question.** Our 80% close range sizes itself from recent swings and lags market-wide jumps (62–65% coverage in bad weeks;
VIX scaling only reached 69%). Does the options market's same-morning range, or a 50/50 blend with ours, do better?

**Data.** Polygon free tier (2 years of daily option aggregates): SPY, QQQ, AAPL, MSFT, NVDA, AMZN, TSLA, META, GOOGL, AMD,
weekly expiries 2024-11-22 → 2026-11-13. For each day, the prior close's ATM weekly straddle (strike fixed at the prior
Friday's spot) → total sd by inverting straddle time value with a normal (Bachelier) model → daily sd = total / √(days left).
4,341 ticker-days, 453 days. Ours = ±Z80 · CLOSE_K · σ_EWMA. Blend = average of the two sds.

**Bug fixed before scoring.** The first version used time value / √(2/π), which is only right at the money; once spot drifts
from the fixed strike it understates the sd (it showed options holding only 52%). Inverting fixes it (scale factor ≈ 0.9).

**Results.** Interval score = width + 10 × miss (lower = better). Calibrated = one scale factor for the options sd fit on the
first half; ~5-session embargo; test = 2025-11-11 → 2026-11-13 (2,168 rows). 4 variants tried (raw/calibrated × options/blend).

| | Ours | Options | Blend |
|---|---|---|---|
| 80% coverage, all days (2y) | 79.8% | 83.4% | 82.7% |
| Coverage, weeks ours held < 70% (778 rows) | 62.5% | 72.8% | 69.9% |
| Coverage, other weeks | 83.6% | 85.7% | 85.5% |
| Average half-width | 2.55% | 2.81% | — |
| Test: coverage all / bad weeks (calibrated) | 79.7% / 60.0% | 77.9% / 66.0% | 80.0% / 64.8% |
| Test: interval score gain vs ours | — | 4.4% | 3.9% |
| Test: HAC t (5 lags, bar 3) | — | 3.22 | 4.25 |
| Test: deflated Sharpe (4 trials, bar 0.95) | — | 0.99 | 1.00 |

Gain in each half (raw): options +2.8% / +4.0%, blend +3.0% / +3.7%. Every ticker's options coverage ≥ ours.

**Verdict.** The calibrated 50/50 blend clears t ≥ 3 and DSR ≥ 0.95 out of sample and is positive in both halves; it keeps
80% coverage overall while lifting bad-week coverage. Limits: 10 liquid large caps only; Polygon prior-close prices, while
live uses Yahoo's delayed chain. Shipping it would change only the display-only day-range card, after approval.

**Code.** `docs/research/scripts/day_range/options_range_backtest.py fetch|analyze` (cache `/home/ubuntu/dr_bt/polygon_opts`).

**Revisit.** Compare with the live options-range log (since 2026-11-17) after 30+ sessions; extend to the full universe.
