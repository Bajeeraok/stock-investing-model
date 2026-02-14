# Data Sources – Integration Tracking & Placeholders

Track all data sources and their status. Add API keys to `config.yaml` when ready.

---

## 0. House style & time cut-off (pro-site parity)

**Price series:** Use one adjusted series everywhere. When FMP is used, we use **FMP adjusted close only** (no raw-close fallback). For MAs, RSI, drawdowns, and returns we use the same adjusted close. Never mix raw and adjusted across indicators.

**Indicator settings (house style):**
- **MAs:** SMA 20 / 50 / 200 on adjusted close (exactly 20 / 50 / 200 trading days).
- **RSI:** 14-period, Wilder’s smoothing (alpha = 1/14), on adjusted close.
- **Volume ratio:** today’s volume ÷ 20-day average volume.

**Return definitions:** Trading days only (not calendar months).  
1m = 21, 3m = 63, 6m = 126, 1y = 252. Return = `P_today / P_start - 1` on adjusted close at both ends.

**Time cut-off:** Decide whether “today” means last official close or a specific intraday snapshot; be consistent. Run the **nightly pipeline** (e.g. `run_daily.py`) after FMP EOD data is stable—e.g. **7–8pm ET**. When comparing to another site, compare at the same phase (both prior close, not your prior close vs their live).

**QA harness:** Run `python backend/scripts/qa_indicators.py` (from repo root or with `cwd=backend`). Compares primary source (FMP when key set, else yfinance) vs reference (yfinance) for MAs, RSI, and 1m/3m/6m returns; logs mean absolute % error. Optional config: `qa_indicators.tickers`, `qa_indicators.period` (default: 1y).

**Chat copilot:** Floating chat button in dashboard. Asks questions using your model data + LLM. Set `OPENAI_API_KEY` (env or `data.openai_api_key` in config). Uses gpt-4o-mini by default; override with `OPENAI_CHAT_MODEL`.

---

## 0b. Free data sources (besides Yahoo)

All of these are free to use; most require a free API key (registration only, no payment).

| Source | API key? | Free tier / notes | Good for | In this project |
|--------|----------|-------------------|----------|------------------|
| **Yahoo Finance** (yfinance) | No | No key; rate limits by IP | EOD prices, volume, analyst consensus, ETFs, indices (^VIX, DXY) | ✅ Primary for OHLCV, cross-asset, indicator validation |
| **FRED** (Federal Reserve) | Yes (free) | Unlimited for normal use | Yields (DGS10), inflation expectations (T10YIE), real rates, macro series | ✅ `fred_client.py` – real yield proxy |
| **Alpha Vantage** | Yes (free) | 5 req/min, 500/day | Prices, technicals, news sentiment, forex | ✅ Client exists; news sentiment when key set |
| **FMP** (Financial Modeling Prep) | Yes (free) | Free tier: limited calls/day | Calendar, treasury, quotes, fundamentals, analyst ratings | ✅ Calendar, 10Y, batch quote, plan check |
| **Finnhub** | Yes (free) | Free tier available | Real-time & historical prices, analyst targets, upgrades/downgrades, news, fundamentals | 🔲 Not integrated; good for validation/analyst data |
| **CFTC** | No (public) or 3rd‑party key | CFTC.gov publishes COT free | Commitment of Traders – speculative positioning (gold, silver, oil) | ✅ `cot_client.py` – extremes for guidelines |
| **Polygon.io** | Yes (free) | Free tier: delayed data | Stocks, options, forex; delayed quotes free | 🔲 Not integrated |
| **TradingEconomics** | Yes | Paid for full API | Calendar, CPI, GDP, etc. | 🔲 Placeholder only |

**For indicator validation and comparison:**
- **Yahoo** – analyst recommendation in `indicator_validation.py` (next-day bias vs consensus).
- **Alpha Vantage** – `alpha_vantage_client.py`: GLOBAL_QUOTE (close), RSI (14); used in `indicator_comparison.py` for close + RSI vs our values (margin of error).
- **Polygon** – `polygon_client.py`: daily aggs last close; used in `indicator_comparison.py` for close comparison.
- **Finnhub** – `finnhub_client.py`: quote (close), stock recommendation; used in `indicator_comparison.py` for close + bias comparison.
- Dashboard shows **indicator comparison** (SPY, QQQ, GLD, SLV): our close/RSI/bias vs AV, Polygon, Finnhub with margin % (price) and margin abs (RSI).

**Summary:** For no key at all: Yahoo + CFTC (and FRED if you get a free key). For more free data with a key: FRED, Alpha Vantage, FMP, Finnhub.

---

## 1. Event Calendar (CPI, PPI, NFP, FOMC, ECB, BoE)

| Source | Config key | Plan/Cost | Status | Use |
|--------|------------|-----------|--------|-----|
| **FMP** | `data.fmp_api_key` | Starter+ | ✅ Integrated | Economic calendar, next 7 days |
| **TradingEconomics** | `data.tradingeconomics_api_key` | Paid | 🔲 Placeholder | Alternative calendar, macro series |

**Guideline:** "Heavy macro week" – CPI + FOMC → reduce size, tighten stops.

### FMP batch quote (stay under 200/day)
- **Config:** `data.use_fmp_batch_quote: true` (default). When `fmp_api_key` is set, the dashboard makes **one** FMP batch-quote request per load for all tickers (watchlist + portfolio + opportunity_universe). Historical OHLCV for indicators comes from yfinance so FMP is only used for latest price. With 15‑min auto-refresh this keeps price-related FMP calls to ~1 per load instead of one per ticker.

---

## 2. Cross-Asset Dashboard (GLD, SLV, DXY, 10Y, VIX)

| Source | Config key | Status | Use |
|--------|------------|--------|-----|
| **yfinance** | – | ✅ In use | DXY, GLD, USO, VIX (via ^VIX) |
| **FMP** | `data.fmp_api_key` | ✅ In use | 10Y Treasury (Starter+) |

**Rules implemented / to implement:**
- DXY up + GLD down = dollar strength pressure
- VIX spike + GLD down = risk-off + metals selloff
- Real yield (10Y − inflation expectations from FRED) = headwind for gold/growth ✅

---

## 3. Extra Data Sources (Placeholders)

### TradingEconomics
- **Config:** `data.tradingeconomics_api_key`
- **Use:** Economic calendar, CPI, GDP, unemployment, etc.
- **Placeholder:** `signals/tradingeconomics_client.py` (stub)
- **URL:** https://tradingeconomics.com/api

### CBOE (VIX, GVZ – Gold Volatility)
- **Config:** `data.cboe_api_key` or use free CBOE data if available
- **Use:** VIX level, GVZ (gold vol) – "market expects big move"
- **Placeholder:** `signals/cboe_client.py` (stub)
- **Note:** Some CBOE data may be free; GVZ = gold volatility index

### CFTC COT (Commitment of Traders)
- **Config:** `data.cftc_api_key` or scrape CFTC.gov (public)
- **Use:** Speculative vs commercial positioning – extreme = risk flag
- **Placeholder:** `signals/cot_client.py` (stub)
- **URL:** CFTC.gov publishes free; some APIs aggregate (Quandl, etc.)

### News / Sentiment
| Source | Config key | Use |
|--------|------------|-----|
| **Alpha Vantage** | `data.alpha_vantage_api_key` | News sentiment (free tier: 5/min, 500/day) ✅ `signals/alpha_vantage_client.py` |
| **Benzinga** | `data.benzinga_api_key` | News, earnings, options flow (placeholder) |
| **FMP** | `data.fmp_api_key` | Stock news (Starter+) |

### ETF Flows (nice-to-have)
| Source | Config key | Use |
|--------|------------|-----|
| **Placeholder** | `data.etf_flows_api_key` | Daily flows SPY, QQQ, GLD, sector ETFs – institutional money flow; systematic feeds usually paid |
| **Module** | `signals/data_source_stubs.get_etf_flows` | Stub; wire when provider/API key is set |

### FRED (Federal Reserve)
- **Config:** `data.fred_api_key` (free at fred.stlouisfed.org)
- **Use:** Yields, inflation expectations, real rates
- **Placeholder:** `signals/fred_client.py` (stub)

---

## 4. Guidelines to Display

| Guideline | Condition | Data needed |
|-----------|-----------|-------------|
| "Heavy macro week" | CPI + FOMC in next 7 days | Economic calendar (FMP/TradingEconomics) |
| "Dollar strength" | DXY up X% today | Cross-asset (DXY) |
| "Real yields rising" | 10Y − inflation expectations up | FRED DGS10 + T10YIE ✅ |
| "Gold IV elevated" | GVZ high | CBOE GVZ |
| "Metals under pressure" | DXY up + GLD/SLV down | Cross-asset |
| "Risk-off" | VIX spike + GLD down | Cross-asset |

---

## 5. Config Placeholders (add to config.yaml)

```yaml
# Data sources – add API keys when ready
data:
  fmp_api_key: ""                    # FMP – calendar, treasury, analysts, insider
  tradingeconomics_api_key: ""       # TradingEconomics – calendar, macro
  alpha_vantage_api_key: ""          # Alpha Vantage – news sentiment (implemented)
  benzinga_api_key: ""               # Benzinga – news, options flow
  etf_flows_api_key: ""              # ETF flows – placeholder; paid/systematic feeds
  fred_api_key: ""                   # FRED – yields, inflation, real rates
  # cboe / cftc – may use public data or third-party aggregators
```

---

## 6. Implementation Checklist

- [x] FMP: economic calendar
- [x] FMP: treasury 10Y
- [x] FMP: plan status / upgrade indicator
- [x] Cross-asset: DXY, GLD, USO, VIX
- [x] Cross-asset rules engine (DXY+GLD, VIX+GLD, real yield)
- [x] Guideline banner ("Heavy macro week", etc.)
- [x] Placeholder stubs: TradingEconomics, Alpha Vantage, FRED, CBOE, CFTC (signals/data_source_stubs.py)
- [ ] Alpha Vantage news sentiment (implement when key added)
- [x] FRED client (signals/fred_client.py) – real yield, inflation exp, 10Y
- [x] FMP fundamentals: profile, key-metrics-ttm (signals/fmp_client.py) – for LT score/fair PE when wired
- [ ] CBOE GVZ (implement when data source decided)
- [x] CFTC COT (signals/cot_client.py) – gold, silver, crude; extreme spec = reversal risk guideline
- [ ] ETF flows (placeholder: data.etf_flows_api_key, get_etf_flows in data_source_stubs) – wire when provider available
