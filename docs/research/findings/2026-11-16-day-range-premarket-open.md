# Day range: pre-market anchor and predicted open
2026-11-16 · Status: shipped, display only

**Question.** NVDA opened at $159.00 (low $158.11) while the card's ranges were centred on Friday's
$162.85 close, so the likely low and 50/80% close ranges missed. Can we do better before the open, and
predict the open itself?

**Data.** 60 days of 5-minute bars with pre-market (yfinance `prepost=True`), 125 tickers, 59 sessions,
7,375 ticker-days. Fit on the first half of the days, checked on the second half. Volatility estimator
check: 10 years of daily bars.

**Results.**

| | From prev close | From pre-market |
|---|---|---|
| Open error (mean abs) | 1.44% | 0.41% |
| Close error (mean abs) | 2.7% | 2.1% |
| Error of the 50% likely low | 1.4% | 0.9% |
| 80% close range on gap days (>1σ) | 45% | 63% |
| Low error on gap days | 3.8% | 1.2% |

- Pre-market close band: 0.80 × σ20 (vs 0.97 from prev close); touch moves × 0.85. Ratio held 0.79–0.84
  in both halves.
- Open band: ±0.19σ (80%) / ±0.17σ (50%) around pre-market; ±0.61σ / ±0.56σ around prev close when there
  is no pre-market print. Both halves agreed within 0.01.
- Volatility estimator: EWMA-20 stayed best across years. Faster EWMA and Parkinson (high-low) did not
  clearly improve coverage, so it was kept. The volatile Oct–Nov 2026 stretch still under-covered
  (~73% inside the 80% band) with every estimator.
- Close vs touch odds: a touch is always at least as likely as closing beyond; the ladder now shows both.

**NVDA 2026-11-16 example.** Old 50% close $159.33–166.44, 75% likely low $161.76. New $156.14–161.87 and
$158.08; actual low $158.11.

**Verdict.** Shipped as display only; never feeds BUY/HOLD/SELL. The 9:20 forecast is logged and scored
against the actual open, post-9:20 low and close (card's "9:20 forecast vs actual" table).

**Code.** `backend/signals/stock_day_range.py`, `backend/signals/day_range_log.py`. Scripts:
`scripts/day_range/fetch.py` → `bt.py` (builds rows) → `ev.py` / `ev2.py` (evaluate / fit k);
`sig10y.py` (volatility estimators).

**Revisit.** After 30+ tracked sessions: refit the k values on live 9:20 data; check whether the
volatile-period under-coverage persists.
