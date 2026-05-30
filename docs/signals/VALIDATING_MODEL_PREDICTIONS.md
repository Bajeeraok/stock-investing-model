# How to Validate How Well the Model Is Doing

This guide lists **concrete ways** to validate your model’s predictions, using what’s already in the repo and a few optional extensions.

---

## 1. **Next-day direction (SPY/QQQ)** — already in the app

**What it validates:** When we say “Bullish” or “Bearish” for the next day, did the market actually go that way?

**Where:** Dashboard → **Analysis** tab → **Model validation**  
**Data:** EOD snapshots (`data/eod/YYYY-MM-DD.json`) with `next_day_outlook` for SPY/QQQ.

**Metrics:**
- **Direction accuracy:** % of days we called Bullish/Bearish and the next day went the right way. Target: >52–55%; 58%+ is strong.
- **Range hit rate:** % of days the actual move was within our ±typical_move. ~68% is a good target if we use ±1σ.

**How to improve:** See **[MODEL_VALIDATION.md](MODEL_VALIDATION.md)** (bias thresholds, state definition, typical_move).

---

## 2. **Multi-horizon & signal accuracy** — already in the app

**What it validates:** “What we said vs what happened” over 5d, 20d, 60d, and whether CONSIDER TRIM / HOLD / HOLD/ADD were followed by the right kind of returns.

**Where:** Dashboard → **Analysis** tab → **Forward tracking**  
**Data:** Same EOD snapshots; compares signal on date D to actual return by D+5, D+20, D+60.

**Metrics:**
- **Avg return by horizon** (5d, 20d, 60d) for SPY/QQQ.
- **Signal accuracy (20d):** When we said CONSIDER TRIM, what was avg 20d return? When we said HOLD/ADD?

**Use:** Check that “CONSIDER TRIM” periods tend to underperform and “HOLD/ADD” to outperform; if not, revisit score/regime bands.

---

## 3. **Score buckets vs forward returns** — backtest (no EOD needed)

**What it validates:** Does a higher composite score today predict better forward returns (1m, 3m, 6m)?

**How to run:**
```bash
cd backend && python scripts/backtest_simple.py
```
**Optional:** Dashboard → **Analysis** → **Backtesting** (uses same logic for GLD, QQQ, SPY).

**What it does:** For each historical date, computes composite score, buckets it (0–30, 30–50, 50–70, 70–100), then measures average 1/3/6 month forward return per bucket.

**What to look for:** Higher score buckets should have higher average forward return. If 70–100 underperforms 30–50, the score or bands need work.

---

## 4. **Daily BUY/HOLD/SELL vs actual forward returns** — needs EOD

**What it validates:** When the model said BUY (or HOLD/SELL) on a given day, how did the market do over the next 1m / 3m / 6m?

**How to run:**
```bash
cd backend && python scripts/backtest_signals.py
```
**Requires:** EOD snapshots (run `run_daily.py` or scheduler / `POST /api/eod/run` regularly).

**Metrics:** Avg return when we said BUY vs HOLD vs SELL (by horizon); precision/recall; directional accuracy. Use to tune `buy_min` / `sell_max` in config.

---

## 5. **Price target accuracy (levels vs close)** — already in the app

**What it validates:** How close today’s price is to our ST target, support, suggested buy, MT band (not a timing prediction, but level accuracy).

**Where:** Dashboard → **Analysis** → **Price target accuracy**  
**CLI:** `cd backend && python scripts/accuracy_price_targets.py` (same-day) or `--forward` (yesterday’s EOD targets vs today’s close).

**Metrics:** Per-ticker err% and MAPE for each level. Config thresholds (e.g. `accuracy.st_target_err_acceptable_pct: 5`) define “acceptable” vs “consider tweak.”

**Use:** If ST target MAPE is high, consider ATR/band tweaks in `target_bands.py`; see `config.accuracy.notes`.

---

## 6. **Target/stop hit rates (ST/MT bands)** — optional script

**What it validates:** Of the days we had a target and stop, did price hit target first, stop first, or neither?

**How to run:**
```bash
cd backend && python scripts/backtest_targets.py
```

**Use:** Target hit ~40–60% is often a reasonable design; if target hit is very low or stop hit very high, bands or volatility inputs may need tuning.

---

## 7. **Regime backtest** — optional

**What it validates:** When regime was UP / NEUTRAL / DOWN, how did forward returns behave?

**How to run:**
```bash
cd backend && python scripts/regime_backtest.py
```
(If present; confirms regime definition is useful for forward returns.)

---

## Suggested validation workflow

| Order | What to do | Purpose |
|-------|------------|--------|
| 1 | Run **backtest_simple.py** | Confirm “higher score → better forward returns” without EOD. |
| 2 | Collect EOD daily (scheduler or `POST /api/eod/run`) | Build history for live validation. |
| 3 | Check **Model validation** and **Forward tracking** in dashboard | Monitor next-day and multi-horizon “prediction vs actual.” |
| 4 | Run **backtest_signals.py** once you have enough EOD | Tune BUY/HOLD/SELL thresholds. |
| 5 | Review **Price target accuracy** | Tune levels (ATR, bands) if MAPE/err% are high. |
| 6 | Optionally run **backtest_targets.py** and **regime_backtest.py** | Refine bands and regime logic. |

---

## Optional extensions (not built yet)

- **Calibration:** Track “when we said X% green, realized green %” over time; adjust bias thresholds if realized drifts.
- **Point forecast error:** If you add an explicit “expected return” (e.g. from state), track MAE/RMSE vs actual next-day or N-day return.
- **Per-ticker validation:** Extend model validation / forward tracking to key portfolio names (not only SPY/QQQ) for “how did our calls do per ticker?”
- **Confusion matrix:** For BUY/HOLD/SELL vs “actual up/down over N days” to see systematic misses (e.g. too many false BUYs in downtrends).

---

## Summary

You already have **five built-in ways** to validate predictions:

1. **Model validation** (next-day direction + range) — Dashboard Analysis.  
2. **Forward tracking** (5d/20d/60d + signal accuracy) — Dashboard Analysis.  
3. **backtest_simple.py** — score buckets vs forward returns.  
4. **backtest_signals.py** — BUY/HOLD/SELL vs forward returns (needs EOD).  
5. **Price target accuracy** — levels vs close (Dashboard + `accuracy_price_targets.py`).

Run EOD daily (or ad-hoc) so 1, 2, and 4 get better over time; use 3 and 5 even without EOD history.
