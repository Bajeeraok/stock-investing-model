# Yesterday's high / low / close as intraday support and resistance
2026-11-18 · Status: tested, not shipped

**Question.** WhatsApp "levels" cards label nearby prices as support/resistance. Before adding yesterday's
high, low and close to the day-range card as support/resistance, do they actually hold more often than
any other price?

**Data.** 5-minute regular-hours bars, 125 tickers, 58 sessions (Aug 24 – Nov 16, 2026). First touch of each
level per day. Bounce = price moves 0.25 × daily σ20 back away from the level before moving the same distance
through it. Placebo = the same level shifted ±0.35σ. Split into first / second half of the days.

**Results (bounce rate, all days).**

| Level | As | Real | Placebo | Real touches |
|---|---|---|---|---|
| Prev close | resistance | 58.7% | 57.4% | 1,323 |
| Prev close | support | 60.7% | 60.5% | 1,327 |
| Prev high | resistance | 58.7% | 59.8% | 1,402 |
| Prev high | support | 60.0% | 61.6% | 485 |
| Prev low | resistance | 54.1% | 59.3% | 577 |
| Prev low | support | 60.8% | 60.9% | 1,501 |

The two halves disagree in sign for most rows (e.g. prev low as support: 65.8% vs 62.9% first half, 55.1% vs
58.8% second half).

**Verdict.** No edge: real levels bounce no more often than nearby random prices; about 6 in 10 touches of
*any* price bounce at this distance. Not added to the card as support/resistance. The same base rate means
"support/resistance" labels on shared levels cards are mostly the base rate, not the level. Options walls
stay labelled "possible support / ceiling, not a guarantee" until live tracking shows otherwise.

**Code.** Script: `docs/research/scripts/day_range/prior_day_levels.py` (needs `m5.pkl`, `d10.pkl`).

**Revisit.** A longer intraday history (1y+), or tracked touch outcomes of the options walls.
