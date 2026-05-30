# Model validation: predicted vs actual (SPY/QQQ)

This doc describes how we validate the next-day outlook and how to use the results to make the model more robust and to fine-tune.

## What we compare

- **As-of date D**: EOD snapshot from `run_daily.py` (or dashboard run) with:
  - **Our bias**: Bullish / Neutral / Bearish from `next_day_bias` (state-based historical % green days).
  - **Our typical range**: ±typical_move % (e.g. SPY ±0.66%) from realized volatility.
- **Next trading day D+1**: Actual close from the following EOD snapshot.
- **Metrics**:
  - **Direction hit**: Bullish and next day return > 0, or Bearish and next day return < 0. Neutral is not counted in accuracy.
  - **Range hit**: Actual next-day return (in %) is within ±our_typical_range_pct.

## How to get validation data

1. **Run EOD daily**  
   After market close, run:
   ```bash
   cd backend && python scripts/run_daily.py
   ```
   This saves `data/eod/YYYY-MM-DD.json` including `next_day_outlook` and `typical_move` for SPY/QQQ. After at least **two** such days, the dashboard section "Model validation: SPY/QQQ predicted vs actual" will show records and summary stats.

2. **Dashboard**  
   The dashboard loads validation from `data/eod/`: for each pair of consecutive EOD dates (D, D+1), it compares prediction as-of D to actual close on D+1. No extra API keys needed; everything comes from EOD files.

## Metrics to watch

| Metric | Meaning | Good target |
|--------|--------|-------------|
| **Direction accuracy** | % of days we called Bullish/Bearish and the next day went the right way | > 52–55% (better than coin flip); 58%+ is strong. |
| **Range hit rate** | % of days the actual move was within our ±typical_move | ~68% if typical_move is ±1σ; adjust if you use a different band. |

- **Neutral** is not scored for direction (we don’t claim up or down). You can still track how often we said Neutral and what the next-day return did, for your own tuning.
- If **direction accuracy** is below 50%, consider: different state definition, longer backtest period, or stricter Bullish/Bearish thresholds (e.g. 58% green for Bullish instead of 55%).
- If **range hit rate** is far from ~68%, our volatility estimate (e.g. 20d) may be off in some regimes; consider high-vol vs normal regime (see `typical_move` high_vol_pct).

## Making validation more robust

1. **Persist predictions and actuals**  
   We already do this: EOD snapshots store `next_day_outlook` and `typical_move`, and the validation layer reads D and D+1 snapshots. Keep `eod_retention_days` (e.g. 90) so you have a rolling history.

2. **Add more tickers (optional)**  
   Validation is currently SPY and QQQ. To add GLD/SLV, extend `_VALIDATION_TICKERS` in `signals/validation.py` and ensure `run_daily.py` includes them in the payload (e.g. `next_day_outlook_for_symbols(["SPY", "QQQ", "GLD", "SLV"])` and same for `typical_move`).

3. **Point estimate (optional)**  
   We currently compare **direction** and **range**. If you add an explicit "estimated return" (e.g. from `avg_return_pct` in the state), you could track MAE or RMSE of that estimate vs actual return for fine-tuning.

4. **Calibration**  
   When we say "58% green days in this state", over time the fraction of next days that close green should be near 58%. You could log (state_key, pct_green, realized_green_pct) per period and adjust thresholds if realized drifts from predicted.

## Fine-tuning levers

- **Bias thresholds** (`signals/next_day_bias.py`): Bullish when `pct_green >= 55`, Bearish when `pct_green <= 45`. Try 58/42 for a more conservative Bullish/Bearish and see direction accuracy.
- **Backtest period**: `run_next_day_backtest(ticker, period="5y")`. Shorter (e.g. 2y) is more reactive; longer is smoother. Validate direction/range over the same horizon you care about.
- **State definition**: States are built from trend, RSI zone, vol regime. If direction accuracy is weak in certain states, consider merging or splitting states, or different RSI/vol thresholds.
- **Typical move**: Currently ±1σ from 20d vol. For "range hit rate" you can compare ±1σ vs ±1.5σ (e.g. high_vol_pct) and see which band matches reality better in different regimes.

## Files

- **EOD payload**: `scripts/run_daily.py` — adds `next_day_outlook` and `typical_move` for SPY/QQQ to `data/eod/YYYY-MM-DD.json`.
- **Validation logic**: `signals/validation.py` — `get_validation_records()` builds records and summary from EOD pairs.
- **API**: `api/routers/dashboard.py` — includes `model_validation` in the dashboard response.
- **UI**: Dashboard section "Model validation: SPY/QQQ predicted vs actual" (table + direction accuracy + range hit rate).
