# Post-earnings move: can we predict the price after earnings?
2026-11-16 · Status: tested; build proposed (display only)

**Question.** Before a report, how well can we predict the size and direction of the next-day move, and
so the price range after earnings?

**Data.** yfinance earnings dates (up to 48 quarters) for our 125 tickers → 102 stocks with history, daily
bars 2015–2026. Reaction = close before the report → close on the first session after it (after-close
reporters: same-day close → next close; pre-market reporters: prior close → report-day close). Needs ≥4
past reports. 3,022 events; fit on < 2021 (1,040), tested on 2021+ (1,982). Median |move| 4.0%.

**Size (test 2021+).**

| Predictor | Mean abs error | Corr with actual | 80% band | 80% coverage: calm / mid / jumpy stocks |
|---|---|---|---|---|
| Same % for every stock | 4.86% | — | ±6.3% | 88 / 64 / 45% |
| 20-day volatility × 1.97 | 4.48% | 0.33 | ±2.22× | — |
| Mean of last 6 reactions (app today) | — | 0.43 | ±2.18× | — |
| Median of last 8 reactions | 4.32% | 0.41 | ±2.14× | 71 / 79 / 91% |
| **Blend: ½ own last 8 + ½ 20-day vol** | **4.16%** | **0.44** | **±1.97×** (50%: ±0.97×) | **80 / 77 / 81%** |

- Blend 80% coverage by year: 2021 87, 2022 78, 2023 77, 2024 74, 2025 83, 2026 77%. Typical 80% band ±9.6%.
- The app's current window is wrong: for pre-market reporters it starts after the reaction, and for
  after-close reporters it spans two days (corr 0.78 with the true move). `tier1_api_bridge` labels
  30-day realized vol × 0.4 as "From options market" — it is not an options price.

**Direction (hit rate; base rate up 51% train / 49% test).** Nothing beats a coin flip in both halves:

| Signal | Train hit | Test hit | Test t (up vs down calls) |
|---|---|---|---|
| Pre-report 20-day drift > 0 | 47.6% | 49.0% | 0.74 |
| 60-day momentum > 0 | 47.1% | 50.4% | 2.02 (train −0.76) |
| Above 50-day | 47.4% | 49.0% | 1.60 |
| Last report moved up | 47.2% | 48.0% | −0.94 |
| Last quarter beat | 52.0% | 48.0% | −2.00 |

**After the report.** Once the post-report open is known, it mostly sets the day: when the gap is
≥0.5× the stock's typical earnings move, the close kept the gap's direction 81% (0.5–1×) and 93% (>1×) of
the time; small gaps only 62%. Drift over the next 20 days did not depend on the reaction's sign (test
+2.11% after up vs +2.33% after down, t −0.33), consistent with the earlier "no post-earnings drift" result.

**NVDA (report 2026-11-17).** App shows ±4.2% with a "Bearish" target $153.25. Blend: typical move 4.9%,
50% range ±4.8%, 80% ±9.7%. Options (2026-11-18 ATM straddle, 156.57): ±8.7%.

**Verdict.** Size is predictable enough for an honest range; direction is not. Proposal: correct the
reaction window, use the blend with 50/80% bands, show the real options straddle next to it, replace the
untested directional target with "direction: no edge", and log each forecast the evening before to score
it after the report. Display only.

**Code.** `scripts/earnings/fetch_er.py` → `er.pkl`; `scripts/earnings/er_move.py` (needs `d10.pkl` from
`scripts/day_range/sig10y.py`). App: `backend/signals/price_targets.py::_compute_earnings_target_block`.

**Revisit.** After ~30 logged reports: compare blend vs options straddle coverage; retest direction with
estimate revisions or the options skew if that data becomes available.

## Implemented (2026-11-16, display only)

- `backend/signals/earnings_move.py`: corrected reaction window, blended typical move, 50%/80% bands, ATM straddle move.
- `backend/signals/price_targets.py::_compute_earnings_target_block`: uses it; `bias` is always Neutral, `directional_target` null.
- `backend/signals/earnings_log.py`: logs forecasts 3:50 PM ET before each report, scores after the reaction close (`DATA_ROOT/earnings_log.json`).
- Revisit after 30+ scored reports: compare 80% coverage and size error vs the options straddle.
