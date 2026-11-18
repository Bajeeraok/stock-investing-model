# Widening the day range when VIX jumps
2026-11-18 · Status: tested, not shipped

**Question.** The 80% close range held only 62–63% of closes in the weeks ending Oct 16 and Nov 6. It sizes itself from
each stock's recent swings, which lag a market-wide jump. Does scaling it by a VIX signal fix those weeks?

**Data.** 125 tickers, daily closes 2015–2026; ^VIX and ^VIX3M closes (known at the prior close).
Range = ±Z80 · CLOSE_K · σ_EWMA; variant multiplies σ by clip(f^a, lo, 3).
36 variants: f ∈ {VIX / its 20-day mean, VIX / VIX3M, VIX / SPY realised vol} × a ∈ {0.25…2} × lo ∈ {1.0, 0.7}.
Picked on 2016–2020 by interval score (width + penalty for misses; lower = better); ~20-session embargo; test 2021-02 → 2026-11.

**Results (test, best train variant = (VIX / 20-day mean)^0.75, floor 0.7).**

| | Baseline | VIX-scaled |
|---|---|---|
| 80% coverage, all days | 78.8% | 78.8% |
| Coverage, weeks the baseline held < 70% (161 days) | 65.3% | 68.7% |
| Coverage, calm days (VIX < 0.95 × 20-day mean) | 82.1% | 78.6% |
| Average half-width | 2.69% | 2.69% |
| Interval score gain | — | 0.4% |
| HAC t (daily gain, 5 lags) | — | 2.11 (bar 3) |
| Deflated Sharpe | — | 0.26 (bar 0.95) |
| PBO (36 variants) | — | 0.0 |

Gain by year: 2021 +0.9%, 2022 +0.2%, 2023 +0.2%, 2024 −0.2%, 2025 +1.3%, 2026 0.0%.

**Verdict.** Consistent in direction (PBO 0) but too small: it moves width from calm days to jumpy days and only lifts
the bad weeks from 65% to 69%. Fails t ≥ 3 and DSR ≥ 0.95. Not shipped. The bad weeks are VIX-day surprises the prior
close can't see; the same-morning options range (logged daily since 2026-11-17) is the candidate to watch instead.

**Code.** `docs/research/scripts/day_range/vix_scaling.py` (needs `d10.pkl`, `vix.pkl`).

**Revisit.** After 30+ sessions of logged options ranges: compare their coverage in jumpy weeks with ours.
