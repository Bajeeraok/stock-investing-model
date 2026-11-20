# Day range in falling markets: storm widening, faster volatility, shock memory, downside skew
2026-11-20 · Status: tested, not shipped

**Question.** Nov 19–20 the 80% close range missed SPY (−2.0%, −3.6%), QQQ (−2.2%, −5.7%) and NVDA (−3.3%, −14.0%).
Does any rule known at the prior close fix the range in stormy markets?

**Data.** 125 tickers, daily closes 2015-01 → 2026-11-16; ^VIX. Baseline = prev close ± Z80 · CLOSE_K · σ_EWMA20.
23 variants: ×{1.1, 1.2, 1.3, 1.5} when SPY is mostly below its 50-day (both sides / downside only), when also 7%+ off
its 60-day high, or when VIX > 25; mixes of span-5 and span-20 σ (25/50/75%, max); widening after a big prior-day move
(σ-units, a ∈ {0.1, 0.2, 0.3}). Picked on 2016–2020 by two-sided interval score; ~20-session embargo; test 2021-02+.

**Results (test).**

| | Baseline | Best train variant (25% span-5 σ) |
|---|---|---|
| 80% coverage, all days | 78.8% | 77.3% |
| Coverage, bad weeks (161 days) | 65.3% | 64.6% |
| Coverage, storm days (418 days) | 76.9% | 75.6% |
| Interval score gain | — | −0.33% (worse) |
| HAC t | — | −4.36 |
| Deflated Sharpe | — | 0.00 |
| PBO (23 variants) | — | 0.28 |

Best test variant (×1.1 when VIX > 25) gained only 0.04%. Every storm/skew widening ≥1.2 lost.
On storm days the baseline misses are symmetric: 11.0% of closes below the range, 11.8% above. Rebound days are as big
as drop days, so widening only the downside or shifting the centre down does not help.

**Holdout 2000–2014 (never used to pick; 53–63 tickers with data, 3,733 days, 1,383 storm days; incl. 2000–02, 2008).**

| | Baseline | Best train variant |
|---|---|---|
| 80% coverage, all days | 78.6% | 77.0% |
| Storm days | 76.7% | 75.4% |
| Bad weeks | 63.4% | 62.8% |
| Sep 2008 – Mar 2009 | 75.3% | 74.1% |
| Interval score gain / HAC t | — | −0.33% / −6.18 |

Best holdout variant (×1.1 when SPY is in a storm and 7%+ off its high): +0.03%, t 0.41. Storm-day misses again
symmetric (11.3% below, 12.1% above). Rerun with `DATA=d00.pkl VIX=vix00.pkl` (yfinance from 1999).

**Verdict.** Nothing passes; not shipped. Storm days run ~3 points under 80% coverage in both periods, and single-day crashes
(NVDA −14%, a ~4–5σ day) sit outside any range that is right on normal days. The same-morning options range
(blend live on 10 tickers since 2026-11-19) is the tested fix; its live review is 2026-12-21.

**Code.** `docs/research/scripts/day_range/storm_range.py` (needs `d10.pkl`, `vix.pkl`).

**Revisit.** With the Dec 21 blend review, or if storm-day coverage in the live log falls below 70% over 30+ sessions.
