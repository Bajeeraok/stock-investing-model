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
- A trim needs a concrete risk: overextended (RSI ≥65 or rich vs the long-term band), plan REDUCE/SELL, or price below
  the Owner (long-term) stop, plus 2/4 trim gates. A low score or AVOID alone shows as "Hold · don't add". There is no "urgent"
  tier: in forward tracking (May–Nov 2026) 4/4-gate trims lost the most (−3.7% net, 43% helped) while 3/4 helped
  (+1.6%, 60%). Per-gate history isn't stored, so the extension-only effect is not yet measured.
- Protect mode is drawdown insurance, not a return booster. 2000–26 S&P 500 (incl. 2000–02 and 2008): half position below
  the 200-day average cut the typical worst drop −66% → −52% for ~1.5%/yr less return.
- Entry bands are for staging or cheaper optional fills. They don't claim that waiting improves returns.
- BTC-USD and ETH-USD use the crypto path. COIN and MSTR use the normal stock path.

## Bands, stops and targets

- Owner (long-term) band, levels, alert and T1/T2 tiers stay at or below the margin-of-safety max add. T3 is a stress
  reference only (at most 50% below spot), never "Target tier".
- Owner mode is more conservative than Swing. Its stop sits below the Owner band.
- Short-term stop = max(1.5 × ATR × prior VIX / 20, 4% of spot). Every BUY has stop < entry < target.
- Short-term band BUY: stop 2 × ATR below price, ATR target 3 × ATR above (both wider for volatile names; R:R 1.5).
  The stop no longer uses the 20-day swing low. A target is
  an upside goal, not the expected move: show how often it was hit, never "missed the target by".
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
- Score against data the model had not seen. Keep the current era's record separate from calls made before it.
- HOLD is never scored right or wrong. ADD is right if price rose, TRIM/REDUCE/SELL/AVOID if it fell.
- Don't bump `MODEL_VERSION` for tuning changes. Every version since `TRACKING_ERA_SINCE` (2026.11.1) is scored as one model so history builds up. Log each change with its date in `signals/model_version.py`.

## Changing the model

- Changes are proposed with out-of-sample evidence (sample size, baseline) and shipped only after the owner's OK.
- Prefer simple recalibration over new features. Fewer than ~30 scored cases = "watch, not enough data".
- Already tested with no edge on S&P 500 large caps (don't re-propose without new data): composite score and price
  factors, point-in-time fundamentals, post-earnings drift, insider clusters, dip-timing for index funds.
- Short-term target distance: closer targets hit more often but lower average P&L (2014–26), so they stay as is.
- Short-term band stop width (2014–26, uptrend entries, 20 days): old stop was hit first 54% of the time. Stop 2× /
  target 3× ATR: average +0.31→+0.45% (2014–19), +0.43→+0.63% (2020–26), losers 57→53%, average gain still above
  average loss. Wider stops (2.5–3×) without a wider target made the average loss bigger than the average gain.

### Promotion bar for new gates

A highlight or experimental rule becomes a gate only if `signals.statistical_validation.promotion_check` passes on
out-of-sample trades:

- 30+ cases, and positive average return after round-trip costs (default 10 bp per trade, more for small caps).
- t-stat ≥ 3 (Harvey, Liu & Zhu), with Newey–West errors when holding periods overlap.
- Deflated Sharpe ≥ 0.95, counting every variant tried (Bailey & López de Prado).
- Chance of backtest overfitting (CSCV) ≤ 50% when a grid of variants was tested.
- Beats the baseline it would replace.
- Walk-forward splits run forward in time with a purge gap, so no embargo is needed. Any k-fold split must add one.

### Research rules on Best setups

- Every saved Research rule (More → Research) shows as a badge on Best setups rows where it is on at the last panel close,
  with its out-of-sample record. Badges are information only.
- A Research run can be approved (`POST /api/research/runs/{id}/approve`) only if its promotion check passed. Approved
  rules that are on for a ticker sort it first within Picks / Next up / Dip watch. Qualification, gates, bands, stops,
  targets and BUY/HOLD/SELL are unchanged (`backend/research/integration.py`, `best_setups.rank`).
- "Our 125" in the screener and event study limits Research to the tracked tickers. They were chosen with hindsight,
  so promotion backtests stay on point-in-time S&P 500 members.
- Research alerts (`backend/research/alerts.py`): after the 8 PM panel update and Best setups build, a rule that is
  approved or clears the promotion bar sends one alert per tracked ticker on the day it turns on (off the session
  before, on at the last close). The alert gives the Best setups band, stop and gate status; when gates are blocked it
  says "watch, gates blocked". Alerts never change gates or BUY/HOLD/SELL.

## Investor rulebook (Plan · Investor rules)

- `backend/signals/investor_rules.py` lists rules from well-known investors (Graham/Buffett, Lynch, Templeton, Paul Tudor
  Jones, Druckenmiller, O'Neil/Minervini, Dalio, Marks, Bogle, Swensen) with live hits on the signals-panel tickers and
  market events (VIX, SPY vs 200-day, 2s10s curve, high-yield spread). `GET /api/investor-rules[?ticker=]`.
- Each rule is tagged `in_model` (already a gate, stop or cap), `highlight` (flag only) or `habit` (process).
- Highlight rules never change BUY/HOLD/SELL. One becomes a gate only after an out-of-sample backtest and the owner's OK.
- Wall St fallback fair values never count as the model's value for "rich vs value".
- A hit is "new" on the first ET day it appears; a rule that stops hitting starts fresh.
- Lynch "story changed" counts only real story events. A plan rebuild after a price move (`HORIZON SHIFT`) never counts.
- On a ticker's Verdict tab, the margin-of-safety and quality-dip hits use that tab's own valuation gate (mode and entry
  tier), not the list-view LT-band shortcut.
- Model fair value stability (`backend/signals/fv_stability.py`): a move of more than 15% from the last accepted value is
  held back unless TTM or forward EPS moved more than 3%, or the new value repeats (within 5%) on a later day.

## Switched-off signals

- **Deep-dip starter exception** (Trend weather failing, 25%+ off the high, 15%+ below the 200-day; buy at RSI < 30 or
  when RSI crosses back above 30; 60-day hold, 10 bps cost, S&P 500 2006–now): every version with a stop (15% or 25%)
  failed the bar (no better than a random pick on the same days, 94–95% overfitting odds). The no-stop versions break
  the stop-before-entry rule and fell 66–80% as strategies. `starter_only` stays off.
- **Velocity / tactical breakout** (RVOL ≥ 2× or upper Bollinger band): 2014–26 S&P 500 backtest, 5-day hold —
  no better than holding the stock; with its stop/target, average ≈ 0% and 65% losers. Live paper: −5.2% over 74.
  Shown as context only: no entry/target/stop, alert, paper trade or Hunter slot (`velocity_tactical.actionable`).
