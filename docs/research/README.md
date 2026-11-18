# Research findings log

Every big analysis gets one file in [`findings/`](findings/) so results are never lost between sessions.
Scripts that produced them live in [`scripts/`](scripts/) and can be rerun.

**Rules**
- A finding is context, not a rule. It changes production only after it clears the promotion bar in
  [`../signals/SIGNAL_RULES.md`](../signals/SIGNAL_RULES.md) and the owner approves it.
- Record negative results too ("tested, not shipped") — they stop us retesting the same idea.
- Screener / event-study runs from the Research tab are saved in its History (with trial counts for
  overfitting odds); write a finding here only when a run drives a decision.

**File template** — `findings/YYYY-MM-DD-<slug>.md`

```
# <Title>
Date · Status: shipped (display only) | shipped (gate) | tested, not shipped | open
Question — what we wanted to know and why.
Data — universe, dates, train/test split, costs, horizon.
Results — table(s), out-of-sample numbers.
Verdict — what we decided and why.
Code — module(s) changed, script(s) to rerun.
Revisit — what would make us look again (e.g. 30+ days of live tracking).
```

## Index

| Date | Finding | Status |
|---|---|---|
| 2026-11-18 | [Yesterday's high/low/close as support/resistance](findings/2026-11-18-prior-day-levels.md) | Tested, not shipped |
| 2026-11-18 | [Day range on earnings reaction days](findings/2026-11-18-earnings-day-range.md) | Shipped (display only) |
| 2026-11-16 | [Post-earnings move: size and direction](findings/2026-11-16-earnings-move.md) | Shipped (display only) |
| 2026-11-16 | [Best setups / full-go forward test](findings/2026-11-16-best-setups-forward-test.md) | Tested; not proven, record split at fix |
| 2026-11-16 | [Bounce zone for dip stocks](findings/2026-11-16-bounce-zone.md) | Shipped, display only |
| 2026-11-16 | [Day range: pre-market anchor and predicted open](findings/2026-11-16-day-range-premarket-open.md) | Shipped, display only |
| 2026-11-14 | [Fair value swings (INTC, NOW, APP, HUM, ORCL…)](findings/2026-11-14-fair-value-swings.md) | Fixed |
| 2026-11-13 | [Deep dips: buy now vs wait, starter tranche](findings/2026-11-13-deep-dip-entry-timing.md) | Tested, not shipped |
