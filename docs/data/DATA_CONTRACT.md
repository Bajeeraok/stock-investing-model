# Data Contract – FMP + FRED Retail Quant Stack

**Purpose:** Map FMP/FRED endpoints → cached fields → which module/screen uses them. Use this for nightly ETL and dashboard refresh.

---

## 1. Nightly price & volume (all tickers)

**Goal:** Regimes, buy/sell zones, ATR/vol, short/medium targets.

| Source | Endpoint / API | Cache fields (per ticker per day) | Module / screen |
|--------|----------------|-----------------------------------|------------------|
| **FMP** | `historical-price-full` (v3) or `historical-price-eod` / `historical-price-eod-light` | `date`, `open`, `high`, `low`, `close`, `volume`, `adjClose` | `signals/providers.py` → `fetch_ohlcv`; `run_daily.py` → MAs, RSI, MACD, ATR, regime |
| **yfinance** (fallback) | `yf.download(..., auto_adjust=True)` | Same OHLCV | Same; used when FMP key missing or fail |

**Engine computes from this:** MAs (10/20/50/200), RSI, MACD, ATR, realized vol, swing high/low, volume ratio.

**ETL path (optional):** `data/prices_daily/{ticker}.csv` or Redis key `prices:{ticker}` with TTL per spec.

---

## 2. Intraday / quote data (dashboard refresh)

**Goal:** Up-to-date prices and P&L without re-running full backtest.

| Source | Endpoint | Cache fields | Module / screen |
|--------|----------|--------------|------------------|
| **FMP** | `stock-batch-quote`, `quote-short` | `symbol`, `price`, `previousClose`, `change`, `changePercent`, `volume` | Dashboard table “close”, portfolio P&L (future) |
| **yfinance** | `Ticker(ticker).fast_info` or `history(period='1d')` | Same | Current: run_signals uses last close from OHLCV |

**Status:** Not yet wired; dashboard uses last close from daily run. Add batch quote when you want live refresh.

---

## 3. Fundamentals & quality / valuation

**Goal:** Long-term score, quality filters, LT fair-value band.

| Source | Endpoint / dataset | Cache fields (TTM + 3–5y history) | Module / screen |
|--------|--------------------|-----------------------------------|------------------|
| **FMP** | `income-statement`, `balance-sheet-statement`, `cash-flow-statement` or “Fundamental Financial Statements” | `revenue`, `operatingIncome`, `netIncome`, `EPS`, `sharesOutstanding`; `totalAssets`, `totalEquity`, `debt`; `operatingMargin`, `netMargin`, `ROE`, `ROIC`, `currentRatio`, `debtToEquity` | LT score, fair PE range (future) |
| **FMP** | `company-key-metrics`, `ratios` | `trailingPE`, `forwardPE`, `priceToBook`, `dividendYield`, `roe`, `operatingMargin` | Same |
| **FMP** | `profile` | `sector`, `industry`, `beta`, `mktCap`, `country` | Ticker detail, sector benchmark, peer comparison |
| **yfinance** | `Ticker.info` | `sector`, `industry`, P/E, etc. | Current: `providers.get_sector_and_industry`, peer fallback |

**Engine uses:** Build LT quality/valuation score; classify style (quality growth vs mature) for fair PE in LT targets.

**ETL path (optional):** `data/fundamentals/{ticker}.json` or Redis `fundamentals:{ticker}`.

**Status:** Profile/sector/industry via yfinance today; FMP fundamentals fetchers added as optional (see `signals/fmp_client.py`).

---

## 4. Analyst estimates & price targets

**Goal:** Refine long-term target band and confidence.

| Source | Endpoint | Cache fields (latest snapshot) | Module / screen |
|--------|----------|--------------------------------|------------------|
| **FMP** | `analyst-estimates` / “Financial Estimates” | `epsEstimateNextYear`, `epsEstimateCurrentYear`, analyst count | `target_bands.py` → fair value band |
| **FMP** | `price-target-consensus`, `price-target-summary` | `priceTargetLow`, `priceTargetAverage`/`Median`, `priceTargetHigh` | Same → blend with fair value for LT_low / LT_high |
| **FMP** | `insider-trading/statistics` | Insider buy/sell stats | Ticker detail modal |

**Engine uses:** Fair-value band from forward EPS × fair PE; blend with priceTargetLow/High; confidence flag when dispersion high.

**Status:** Integrated in `run_daily.py`, `ticker_detail.py`, `target_bands.py`; cached via `signals/cache.py`.

**ETL path (optional):** `data/analyst/{ticker}.json` or Redis `analyst:{ticker}`.

---

## 5. Macro & risk regime (index-level)

**Goal:** Risk-on/off overlay, position size, when to trust buy zones.

| Source | Endpoint / API | Cache fields | Module / screen |
|--------|----------------|--------------|------------------|
| **FMP** | `treasury-rates` | 10Y, 2Y, etc. | `fmp_client.get_10y_rate`; cross_asset “10Y Treasury” |
| **FMP** | `economic-calendar` | Next 7 days events | Guidelines “Heavy macro week” |
| **FMP** | Index historical (SPX, NDX, sector) | Same as prices_daily | Regime overlay (future) |
| **FRED** | Series: `DGS10`, `T10YIE`, `FEDFUNDS`, `CPIAUCSL`, `UNRATE` | Latest value per series | Real yield = 10Y − T10YIE; “Real yields rising” guideline |
| **yfinance** | DXY, GLD, USO, VIX | `close`, `pct_change` | `cross_asset.run_cross_asset_daily`; guidelines |

**Engine uses:** Market regime score (risk-on / neutral / risk-off); tighten/loosen buy zone and stop rules.

**Status:** FMP treasury + calendar + DXY/GLD/USO/VIX integrated; FRED client added for real yield and CPI/unemployment.

**ETL path (optional):** `data/macro/latest.json` or Redis `macro:latest`.

---

## 6. Optional phase 2: positioning / flows

| Source | Use | Module |
|--------|-----|--------|
| **CFTC** | COT for gold, silver, index futures (free) | “Spec positioning extreme” guideline |
| **FMP** | ETF/fund holdings | Sector/theme exposure |
| **ETF flows** | Shares outstanding + price or alt-data | Risk-on/off confirmation |

**Status:** Placeholder; not required for v1.

---

## 7. Nightly ETL folder structure (reference)

When you add a nightly ETL job, use a structure like:

```text
data/
  prices_daily/       # FMP or yfinance OHLCV per ticker (date, o, h, l, c, v, adjClose)
  fundamentals/       # FMP statements + key-metrics + profile per ticker
  analyst/            # FMP analyst-estimates + price-target-consensus per ticker
  macro/              # FRED series + FMP treasury/calendar snapshot
  eod/                # Existing: daily dashboard snapshot YYYY-MM-DD.json
```

**Cache policy (Redis):** See `signals/cache.py`. No cache for live price/MAs/RSI/MACD; cache backtest, economic calendar, fundamentals, price targets, insider stats with TTLs as defined.

---

## 8. Config keys (config.yaml)

| Key | Purpose |
|-----|---------|
| `data.fmp_api_key` | FMP: prices, treasury, calendar, analyst, insider |
| `data.fred_api_key` | FRED: yields, inflation expectations, real yield |
| `data.period` | Default history period (e.g. 5y) for OHLCV |
| `data.tradingeconomics_api_key` | Optional alternative calendar |
| `data.alpha_vantage_api_key` | Optional news sentiment |
| `data.benzinga_api_key` | Optional news/options flow |

---

## 9. How this maps to your screens

| Screen / section | Data used |
|------------------|-----------|
| **Daily Signals** | Section 1 (OHLCV → MAs, RSI, MACD, regime); Section 4 (analyst → LT band); Section 5 (macro in guidelines) |
| **Portfolio doctor** | Section 1 (prices for P&L); Section 3 (sector/industry for allocation) |
| **Ticker detail modal** | Section 1 + 3 + 4 (MAs, fundamentals, analyst, insider); Section 5 (context) |
| **Cross-asset + guidelines** | Section 5 (DXY, GLD, USO, VIX, 10Y, FRED real yield, economic calendar) |
| **Backtesting** | Section 1 (historical OHLCV only) |
| **2026 best tickers / opportunities** | Section 1 + 3 (score, regime); Section 4 optional |
