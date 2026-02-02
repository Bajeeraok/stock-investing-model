# Backtesting Daily Signals & Model Feedback

## Current Behavior

**The model does NOT auto-adjust** based on prediction vs actual outcomes. It uses fixed thresholds (buy_min, sell_max) from config. To improve accuracy, you need to:

1. **Collect EOD snapshots** – run `run_daily.py` daily (e.g. after market close) so `data/eod/` fills with dated snapshots.
2. **Backtest** – compare past predictions against actual forward returns.
3. **Tune** – adjust `buy_min` / `sell_max` in config based on backtest results.

## Backtest Scripts

### 1. `backtest_simple.py` (score buckets vs forward returns)

```bash
cd backend && python scripts/backtest_simple.py
```

- Uses full price history to compute composite score at each date.
- Buckets by score (0–30, 30–50, 50–70, 70–100).
- Computes average 1/3/6 month forward return per bucket.
- Use to validate: higher score → better forward returns.

### 2. `backtest_signals.py` (daily signals vs actual EOD)

```bash
cd backend && python scripts/backtest_signals.py
```

- Requires EOD snapshots from `run_daily.py`.
- Uses your actual daily predictions (BUY/HOLD/SELL).
- Compares against 1-month forward return.
- Reports:
  - Avg return when model said BUY / HOLD / SELL
  - Hit rate (BUY → positive return, SELL → negative)
  - Suggested threshold tweaks

## Error Margin & Model Tuning

### Metrics to Watch

| Metric | Meaning |
|--------|---------|
| **BUY avg return** | When score ≥ buy_min, avg forward return. Should be positive. |
| **SELL avg return** | When score ≤ sell_max, avg forward return. Should be negative. |
| **Directional accuracy** | % of BUY/SELL predictions that moved in the expected direction. |
| **Hit rate** | % of BUY signals that had positive forward return. |

### Suggested Adjustments

- **BUY underperforming** (avg return &lt; 0) → raise `buy_min` (e.g. 72–75).
- **SELL too early** (avg return &gt; 0 when we said SELL) → lower `sell_max` (e.g. 25–28).
- **HOLD too wide** → narrow the band (e.g. buy_min 72, sell_max 28).

### Future: Auto-Feedback Loop

A possible enhancement:

1. Store each day’s signals in EOD snapshots (already done).
2. Periodically (e.g. weekly) run backtest_signals.
3. If BUY hit rate &lt; 55%, suggest raising buy_min.
4. Persist suggested thresholds in a separate file for review.

## Excel Template for Portfolio Upload

| ticker | quantity | cost_basis |
|--------|----------|------------|
| AAPL   | 10       | 150.00     |
| MSFT   | 5        | 320.00     |
| SPY    | 20       |            |

Optional columns: `symbol` (alias for ticker), `qty` (alias for quantity), `cost` (alias for cost_basis).
