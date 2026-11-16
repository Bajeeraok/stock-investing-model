# Deep dips: buy now vs wait for the 50-day, and the starter tranche
2026-11-13 · Status: tested, not shipped

**Question.** NVDA was ~$160 with its 50-day at ~$200. Does waiting for the 50-day cost the rebound? Should
a small stop-sized starter be allowed while Trend weather fails?

**Data.** Research tab event study, S&P 500, 2006 → 2026. Trigger: ≥25% off the high and ≥15% below the
200-day. Hold 60 days, after round-trip costs. Survivorship: delisted stocks are missing, so results are
optimistic.

| Entry | Stop | Trades | Avg | Win | vs SPY same days | Worst |
|---|---|---|---|---|---|---|
| Buy now (RSI < 30, 20% under 50-day) | none | 1,835 | +9.0% | 65% | +1.7% | −95% |
| First turn (RSI back above 30) | none | 3,084 | +7.2% | 63% | +1.7% | −90% |
| Wait for the 50-day | none | 3,101 | +2.6% | 57% | +0.1% | −95% |
| Buy now | 15% | 2,367 | +4.2% | 44% | +0.8% | −52% |
| Buy now | 25% | 2,100 | +5.0% | 54% | −3.4% vs random pick | — |
| First turn | 25% | 3,617 | +5.3% | 57% | −1.1% vs random pick | — |

- SPY made +7.4% over the same windows; vs a random stock on the same days the dip added only +0.6%.
- 2007–08: −7% to −10% per trade, then +45% in 2009. As a full strategy: −80% max drawdown, 3.7%/yr vs
  SPY 10.8%/yr.
- Every stop version underperformed a random pick on the same days; probability of overfitting 94–95%.

**Verdict.** Waiting for the 50-day gives up most of the rebound, but no stop-before-entry version clears
the promotion bar, and no-stop versions break the core rule. Starter-tranche exception not shipped;
Trend weather gate unchanged. The no-stop runs were deleted from Research History (still counted as
trials).

**Revisit.** A starter rule that beats a random same-day pick with a stop, t ≥ 3, deflated Sharpe ≥ 0.95.
