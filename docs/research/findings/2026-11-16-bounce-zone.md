# Bounce zone for dip stocks
2026-11-16 · Status: shipped, display only (ticker Day range card)

**Question.** For a stock in a dip, can we predict where it bottoms, so we don't miss cheaper prices — or
miss the trade by waiting?

**Data.** 124 of our 125 tickers, daily bars 2015-06 → 2026-11. Trigger: close ≥15% below 252-day high
and below 50-day average. Target: lowest low over the next 40 sessions, in units of the stock's 20-day
EWMA daily σ. Fit quantiles on 2015–2020 (19,923 events), test 2021–2026 (48,902 events). Overlapping
events (consecutive days of the same dip), so counts overstate independent samples.

**Fitted further fall (σ20 units, train):**

| Drawdown | 10th pct | Median | 90th pct |
|---|---|---|---|
| > 40% | −11.85 | −3.32 | −0.26 |
| 25–40% | −11.21 | −2.69 | −0.27 |
| 15–25% | −11.60 | −3.41 | −0.36 |

**Out-of-sample (2021–2026):**

| Metric | Result |
|---|---|
| Further fall to the 40-day low | median −11.3% |
| 80% zone width | ~31% of price |
| Actual low inside 80% zone | 84.8% (by year 2021–26: 83, 87, 85, 86, 81, 86%) |
| Median error of predicted bottom | 7.2% (naive "bottom is today": 11.3%) |
| Limit buy at median bottom | filled 58%, +7.5% at 60 days |
| Limit buy at top of zone | filled 93%, +7.0% at 60 days |
| Buy now | +7.7% at 60 days |
| Trades that never reached the median limit | +23.1% buying now (top-of-zone misses: +33.4%) |

**Verdict.** The zone is honest (coverage holds every year) but wide, and waiting for it did not beat
buying now — the trades that never dipped were the best rebounds. Shown on dip-stock cards as context,
labelled "not a reason to wait"; the guidance stays "stage entries with a stop". Not a gate, not a signal.

**Code.** `backend/signals/bounce_zone.py` (constants above), added to the day-range payload in
`compute_stock_day_range`. Script: `scripts/day_range/bounce.py` (needs `d10.pkl` from `sig10y.py`).

**Revisit.** If a narrower zone (e.g. using support levels or volume) cuts the 7.2% error a lot, or if
limit entries start beating buy-now out of sample.
