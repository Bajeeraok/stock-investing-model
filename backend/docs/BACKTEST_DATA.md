# Backtest data honesty & exclusions

This document describes what the **Phase 4 backtest** (`scripts/backtest_simple.py`) assumes about prices, events, and universes. Use it when interpreting bucket returns or claiming long-horizon “edge.”

## Adjusted close (Yahoo Finance)

- Daily series come from **yfinance** with **`auto_adjust=True`** (see `signals/fetcher.py`).
- **Splits and cash dividends** are reflected in the adjusted close used for returns. That is the standard retail shortcut for a **total-return–like** equity series without modeling dividend reinvestment explicitly.
- **Limits:** Adjusted series can be revised by the vendor; extreme corporate actions may still distort short windows. This is **not** CRSP-style point-in-time fundamentals or institutional total-return indexes.
- **FX, ADRs, halts:** Not modeled separately; thin names may show stale prices.

## Earnings exclusion (`backtest.earnings_exclusion`)

- When **`enabled: true`** and **`days_before: N`**, the backtest **skips** any bar whose **next** earnings-related date (from FMP) falls within **0–N calendar days** ahead (including the report day).
- **Requires** `data.fmp_api_key` (or env). **ETFs / index symbols** in a built-in skip list do not call FMP.
- **Caveat:** Dates come from **historical** FMP `historical/earning_calendar` (fallback: `earnings-surprises`). That improves short-horizon signal-to-noise but is **not** a fully point-in-time “what the market knew on that day” calendar. Use for **cleaner** short-horizon stats, not legal-grade event studies.

## Survivorship & universe (`backtest.universe`)

- **`mode: none`:** Backtest uses the ticker you pass; no membership filter.
- **`mode: full_history`:** Drops tickers with fewer than **`full_history_min_bars`** adjusted daily rows for `data.period`. Reduces obvious “no history yet” artifacts; **does not** replace official index membership.
- **`mode: membership_csv`:** You maintain **`ticker,start_date,end_date`** rows; only names active on **`as_of_date`** (or today) are run in the batch CLI. Lets you encode **your own** universe rules (e.g. from public index change lists) without a constituents subscription.

## Regime labels (`backtest.regime`)

- **`benchmark` / `ma_days`:** Each walk-forward test window gets a **`spy_regime`** tag: **bull** if benchmark close \> SMA(`ma_days`), **bear** if below, **neutral** in a narrow band, else **unknown** if history is short.
- **`spy_regime_summary`** on the main backtest: percent of **scored** bar days in bull / bear / neutral for the same benchmark series (aligned to the ticker’s calendar).
- These fields are **descriptive only** (split stats by coarse market regime). They do **not** enter the composite score.

## What this does *not* do

- **Survivorship-free index replication** without you supplying membership or a vendor dataset.
- **Delisting return** modeling for names that cease trading.
- **Execution:** Spreads, borrow, and market impact are **not** in the score; only the configured round-trip **`transaction_cost`** (unless you extend the script).

For implementation entry points, see `signals/backtest_earnings.py`, `signals/backtest_universe.py`, and `signals/fetcher.py`.
