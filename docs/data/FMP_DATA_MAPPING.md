# FMP Data Mapping – One Provider for Everything

Research shows **Financial Modeling Prep (FMP)** can cover almost all data needs for the stock investing model. Below is what FMP offers and which plan unlocks each feature.

**Base URL (stable API):** `https://financialmodelingprep.com/stable/`  
**Auth:** Append `?apikey=YOUR_KEY` (or use header).

---

## Plan Tiers (Personal Use)

| Plan | Price | Key limits |
|------|-------|------------|
| **Basic** | Free | 250 calls/day, EOD historical, profile, reference |
| **Starter** | $22/mo | 300 calls/min, 5yr history, news, crypto, forex |
| **Premium** | $59/mo | 750 calls/min, 30yr history, intraday, technicals, calendars |
| **Ultimate** | $149/mo | 3000 calls/min, **13F institutional**, earnings transcripts, ETF holdings |

---

## Data Coverage by Category

### 1. Price & Chart Data (replace yfinance)

| Need | FMP Endpoint | Plan |
|------|--------------|------|
| EOD OHLCV | `/historical-price-eod/full?symbol=AAPL` | Basic |
| EOD light (date, close, volume) | `/historical-price-eod/light?symbol=AAPL` | Basic |
| Dividend-adjusted | `/historical-price-eod/dividend-adjusted?symbol=AAPL` | Basic+ |
| Intraday 1/5/15/30/60 min | `/historical-chart/1min?symbol=AAPL` | Premium |
| Real-time quote | `/quote?symbol=AAPL` | Starter |
| Batch quote | `/batch-quote?symbols=AAPL,MSFT` | Starter |

**Action:** Use FMP as primary EOD source; more reliable than yfinance.

---

### 2. Fundamentals & Financials

| Need | FMP Endpoint | Plan |
|------|--------------|------|
| Income statement | `/income-statement?symbol=AAPL` | Basic |
| Balance sheet | `/balance-sheet-statement?symbol=AAPL` | Basic |
| Cash flow | `/cash-flow-statement?symbol=AAPL` | Basic |
| Key metrics (P/E, ratios) | `/key-metrics?symbol=AAPL` | Basic |
| Financial ratios | `/ratios?symbol=AAPL` | Basic |
| TTM (trailing 12 months) | `/income-statement-ttm`, etc. | Basic |
| Piotroski / Altman Z | `/financial-scores?symbol=AAPL` | Basic |
| DCF / enterprise value | `/enterprise-values?symbol=AAPL` | Basic |

---

### 3. Company Profile & Peers (already using)

| Need | FMP Endpoint | Plan |
|------|--------------|------|
| Profile (sector, industry, market cap) | `/profile?symbol=AAPL` | Basic |
| Peers | `/stock-peers?symbol=AAPL` | Basic |
| Market cap (historical) | `/market-capitalization?symbol=AAPL` | Basic |
| Share float | `/shares-float?symbol=AAPL` | Basic |

---

### 4. Earnings & Calendars

| Need | FMP Endpoint | Plan |
|------|--------------|------|
| Earnings calendar | `/earnings-calendar` | Starter |
| Earnings by symbol | `/earnings?symbol=AAPL` | Starter |
| Earnings transcripts | `/earning-call-transcript?symbol=AAPL&year=2024&quarter=1` | **Ultimate** |
| Dividends | `/dividends?symbol=AAPL` | Basic |
| Dividends calendar | `/dividends-calendar` | Starter |
| Splits | `/splits?symbol=AAPL` | Basic |
| IPOs calendar | `/ipos-calendar` | Starter |

---

### 5. Analyst Data

| Need | FMP Endpoint | Plan |
|------|--------------|------|
| Analyst estimates (EPS, revenue) | `/analyst-estimates?symbol=AAPL` | Starter |
| Price target summary | `/price-target-summary?symbol=AAPL` | Starter |
| Price target consensus | `/price-target-consensus?symbol=AAPL` | Starter |
| Grades (upgrades/downgrades) | `/grades?symbol=AAPL` | Starter |
| Grades summary (strong buy/buy/hold) | `/grades-consensus?symbol=AAPL` | Starter |

---

### 6. Form 13F & Institutional Ownership

| Need | FMP Endpoint | Plan |
|------|--------------|------|
| Latest 13F filings | `/institutional-ownership/latest` | **Ultimate** |
| Holdings extract by CIK | `/institutional-ownership/extract?cik=...&year=2023&quarter=3` | **Ultimate** |
| Holder performance summary | `/institutional-ownership/holder-performance-summary?cik=...` | **Ultimate** |
| Positions by symbol | `/institutional-ownership/symbol-positions-summary?symbol=AAPL` | **Ultimate** |
| Industry breakdown by holder | `/institutional-ownership/holder-industry-breakdown?cik=...` | **Ultimate** |

---

### 7. Insider Trades

| Need | FMP Endpoint | Plan |
|------|--------------|------|
| Latest insider trades | `/insider-trading/latest` | Starter |
| Search by symbol | `/insider-trading/search?symbol=AAPL` | Starter |
| Insider stats by symbol | `/insider-trading/statistics?symbol=AAPL` | Starter |

---

### 8. News & Press Releases

| Need | FMP Endpoint | Plan |
|------|--------------|------|
| Stock news by symbol | `/news/stock?symbols=AAPL` | Starter |
| General news | `/news/general-latest` | Starter |
| Press releases | `/news/press-releases?symbols=AAPL` | Starter |

---

### 9. Technical Indicators (optional – we compute ourselves)

| Need | FMP Endpoint | Plan |
|------|--------------|------|
| SMA, EMA, RSI, etc. | `/technical-indicators/sma?symbol=AAPL&periodLength=20` | Premium |

---

### 10. ETFs, Crypto, Forex, Commodities

| Need | FMP Endpoint | Plan |
|------|--------------|------|
| ETF holdings | `/etf/holdings?symbol=SPY` | **Ultimate** |
| ETF sector weightings | `/etf/sector-weightings?symbol=SPY` | **Ultimate** |
| Crypto quotes | `/batch-crypto-quotes` | Starter |
| Forex quotes | `/batch-forex-quotes` | Starter |
| Commodity quotes | `/batch-commodity-quotes` | Starter |
| Index quotes (^GSPC, etc.) | `/batch-index-quotes` | Starter |

---

### 11. Economics & Macro

| Need | FMP Endpoint | Plan |
|------|--------------|------|
| Treasury rates | `/treasury-rates` | Basic |
| Economic indicators (GDP, CPI, etc.) | `/economic-indicators?name=GDP` | Basic |
| Economic calendar | `/economic-calendar` | Starter |
| Market risk premium | `/market-risk-premium` | Basic |

---

### 12. SEC Filings

| Need | FMP Endpoint | Plan |
|------|--------------|------|
| Latest 8-K | `/sec-filings-8k?from=...&to=...` | Basic |
| SEC filings by symbol | `/sec-filings-search/symbol?symbol=AAPL` | Basic |
| 10-K/10-Q JSON | `/financial-reports-json?symbol=AAPL&year=2024&period=FY` | Basic |

---

## What’s NOT in FMP (or limited)

| Need | Alternative |
|------|-------------|
| **Unusual options flow** | Unusual Whales, FlowAlgo, Cheddar Flow |
| **Sentiment scores** | Build from FMP news + simple NLP, or Alpha Vantage news sentiment |
| **Dark pool / lit ratio** | Typically not in retail APIs |
| **Real-time L2 order book** | Polygon, IEX (higher cost) |

---

## Recommended Implementation Path

### Phase 1 – Starter plan ($22/mo)
- Replace yfinance with FMP for EOD, profile, peers, earnings
- Add analyst estimates, price targets, grades
- Add insider trades, news
- Add economic calendar

### Phase 2 – Premium ($59/mo) if needed
- Intraday for finer signals
- Longer history (30yr) for backtests
- Technical indicators if you prefer FMP over local calc

### Phase 3 – Ultimate ($149/mo) for full coverage
- 13F institutional ownership (whale tracking)
- Earnings transcripts
- ETF holdings for sector/portfolio analysis
- Higher rate limits

---

## Config Update

Add FMP API key to `config.yaml`:

```yaml
data:
  fmp_api_key: "YOUR_KEY"
  period: 5y
```

Then use FMP in `signals/providers.py` and `signals/fetcher.py` for OHLCV, earnings, peers. The codebase already supports FMP; ensure the key is set and consider migrating fully from yfinance for critical paths.
