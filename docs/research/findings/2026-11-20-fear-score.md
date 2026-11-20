# Fear & Greed-style fear score as a 20-day SPY signal
2026-11-20 · Status: tested, not shipped

**Question.** Does a CNN-style fear score (high = fear) say anything about SPY's next 20 sessions?

**Data.** SPY, ^VIX, ^VIX3M, HYG, IEF, TLT daily closes 2007–2026 (yfinance). Score = mean trailing-252-day percentile of 6
inputs: VIX, VIX/VIX3M, SPY below its 125-day average, junk-bond demand (HYG vs IEF, 20d), safe-haven demand (TLT vs SPY,
20d), SPY drawdown from its 60-day high. Forward 20-session SPY return minus 0.2% cost; excess vs all days; HAC t (20 lags);
3 thresholds tried. Train 2008–2016, test 2017–2026.

| Test 2017–2026 | Days (non-overlapping) | 20d return | Up | HAC t (bar 3) | DSR (bar 0.95) |
|---|---|---|---|---|---|
| All days | — | 1.00% | 68% | — | — |
| Fear ≥ 70 | 514 (26) | 1.57% | 65% | 0.69 | 0.88 |
| Fear ≥ 80 | 310 (16) | 1.60% | 62% | 0.56 | 0.74 |
| Fear ≥ 90 | 165 (9) | 1.64% | 59% | 0.45 | 0.56 |

Train was similar (t 0.13–0.86). Score on 2026-11-20: 97.

**Verdict.** Higher average after fear, but fewer up periods and nowhere near t ≥ 3: a few big rebounds drive the mean.
Only ~16–26 independent episodes per half. Not shipped; the Storm meter stays as history-only education.

**Code.** Inline in the session; inputs above are enough to reproduce.
