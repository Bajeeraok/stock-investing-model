# Signal rules — the contract every signal must follow

> Canonical product rules for Thrive Alpha signals (stocks and ETFs). Code, the nightly ticker-consistency audit
> (`backend/signals/ticker_consistency_audit.py`) and the weekly tuning review check against this file.
> Change a rule here first, with the owner's OK, then in code. Educational decision support, not personal advice.

## Core principle: losses small and rare, gains bigger

The goal is accurate signals for every stock and ETF. Not losing money on a ticker comes first. Beating SPY/QQQ is a
second-level check.

1. **No open-ended losses.** Every BUY/add has a stop and a maximum loss fixed before entry.
2. **When unsure, don't buy.** HOLD/AVOID is the default. Missing a gain is better than taking an unplanned loss.
3. **Every signal earns its place.** Each signal type must show positive average P&L per ticker on data it never saw.
   One that loses money is fixed or switched off.
4. **Judge the worst case, not just the hit rate.** Track loss rate, average loss vs average gain, and the worst loss.
5. **Benchmarks come second.** SPY/QQQ and same-stock buy-and-hold are checked after a signal is shown to be
   profitable on its own.

**How it is measured:** the per-ticker loss scorecard (`build_loss_scorecard` in
`backend/signals/forward_tracking_metrics.py`, Track tab "Loss check") scores ADD/BUY calls by P&L and trim/avoid
calls by drops avoided vs gains missed, over 5 and 20 trading days, current model first. Fewer than 10 calls = too few
to judge. The audit raises `buy_calls_losing_money`, `exit_calls_costing_money` and `buy_losses_bigger_than_gains`.

## Decision semantics

- HOLD is the ordinary default. Ordinary stocks never get a score-only BUY or SELL.
- An actionable entry needs every gate cleared. Price alerts say which gates are still locked.
- REDUCE/SELL is for real risk or a plan's own stop/target, not a low score.
- AVOID means don't open or add. It does not mean sell.
- Protect mode is drawdown insurance, not a return booster.
- Entry bands are for staging or cheaper optional fills. They don't claim that waiting improves returns.
- BTC-USD and ETH-USD use the crypto path. COIN and MSTR use the normal stock path.

## Bands, stops and targets

- Owner (long-term) band, levels, alert and T1/T2 tiers stay at or below the margin-of-safety max add. T3 is a stress
  reference only (at most 50% below spot), never "Target tier".
- Owner mode is more conservative than Swing. Its stop sits below the Owner band.
- Short-term stop = max(1.5 × ATR × prior VIX / 20, 4% of spot). Every BUY has stop < entry < target.
- "Next level" = band top when price is above the band, band low when inside, same wording in both modes.
- Margin of safety shown = (FV − price) / FV.

## Best setups

- Long-term picks must be at or below the max add. Only medium-term picks get the 3% near-band allowance.
- Intraday refreshes recheck picks against the live page ("No longer qualifies" + reason).
- The 8 PM EOD list is the official, tracked one and is never overwritten intraday.

## Market Pulse

- SPY uses prior-session VIX. QQQ uses prior-session VXN, never VIX. Live prints are display-only.
- Support/resistance are reference levels. Show the chance to reach a level today, never that it will hold.

## Data and tracking

- Official 8 PM EOD snapshots are never overwritten by intraday runs.
- Score against data the model had not seen. Keep each model version's record separate.
- HOLD is never scored right or wrong. ADD is right if price rose, TRIM/REDUCE/SELL/AVOID if it fell.
- Bump `MODEL_VERSION` on any change to odds or gates.

## Changing the model

- Changes are proposed with out-of-sample evidence (sample size, baseline) and shipped only after the owner's OK.
- Prefer simple recalibration over new features. Fewer than ~30 scored cases = "watch, not enough data".
- Already tested with no edge on S&P 500 large caps (don't re-propose without new data): composite score and price
  factors, point-in-time fundamentals, post-earnings drift, insider clusters, dip-timing for index funds.
