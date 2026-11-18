# Day range on earnings reaction days
2026-11-18 · Status: shipped, display only

**Question.** On NVDA's reaction day the day-range card's 80% close range ($149.53–161.63) was a third
of the options market's ($136.85–176.60) and narrower than our own earnings range. How badly do the normal
bands miss on reaction days, and what width fixes it?

**Data.** 3,223 reported earnings (102 stocks, 2015–2026, daily bars). Fit on reports before 2021
(1,118), tested on 2021+ (2,105). Reaction = close before the report → first close after it. "After the
report" uses the reaction-day open as a proxy for the pre-market price.

**Results (80% close range, share of closes inside).**

| Moment | Normal band | Fix | Train | Test 2021+ |
|---|---|---|---|---|
| Before the report (from prior close) | 32% | earnings 80% move | 79% | 78% |
| After the report (from open / pre-market) | 46% | σ20 × 2.20 | 80% | 80% |

By year (after the report, test): 75–85%. By stock volatility: calm 73%, mid 81%, jumpy 85%.

**Verdict.** Normal bands are far too narrow on reaction days. The card now widens the range (and the
ladder / level odds with it) on the session whose close is the first after a report: the earnings 80% move
before the report, σ20 × 2.20 once it is out. The intraday version reuses the ×2.20 untested at specific
times of day; live tracking (`event` saved with each snapshot) will check it. Display only.

**Code.** `backend/signals/stock_day_range.py` (`EVENT_POST_K`, `_earnings_event`, `build_day_range(event=)`).
Script: `docs/research/scripts/earnings/reaction_day_range.py` (needs `d10.pkl`, `er.pkl`).

**Revisit.** 30+ tracked reaction days, or if calm-stock coverage stays near 73% (a typical-move-based
width `max(normal, 0.81 × typical move)` was the alternative: 78% test).
