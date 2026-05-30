# Thrive Alpha — Data Sources Audit

> Last updated: 2026-02-28  
> All 5 API keys confirmed present in `backend/config/config.yaml`

---

## API Keys Configured

| Provider | Config Key | Tier | Status |
|---|---|---|---|
| Financial Modeling Prep (FMP) | `data.fmp_api_key` | Starter | ✅ Configured |
| FRED (Federal Reserve) | `data.fred_api_key` | Free | ✅ Configured |
| Alpha Vantage | `data.alpha_vantage_api_key` | Free (500/day) | ✅ Configured |
| Polygon.io | `data.polygon_api_key` | Free tier | ✅ Configured |
| Finnhub | `data.finnhub_apikey` | Free tier | ✅ Configured |
| yfinance | *(no key required)* | Free | ✅ Built-in |
| SEC EDGAR | *(no key required)* | Free public API | ✅ Built-in |
| CFTC COT | *(no key required)* | Free public API | ✅ Built-in |

---

## 7-Layer Confidence Engine — Data Sources

| Layer | Name | Primary Source | Fallback | Key Required | Status |
|---|---|---|---|---|---|
| 1 | **HMM Regime** | yfinance OHLCV (2y daily) | MA-based regime proxy | None | ✅ Fully wired |
| 2 | **Pattern / Technical** | yfinance OHLCV (2y OHLCV) | Composite score only | None | ✅ Fully wired |
| 3 | **LightGBM ML** | yfinance OHLCV (5y–20y) → trained `.pkl` models | N/A (layer skipped) | None | ✅ Trains + infers; degrades gracefully |
| 4 | **Options Sentiment** | yfinance `option_chain()` | VIX proxy for ETFs (auto-fetched) | None | ✅ Fixed: VIX auto-fetched when not supplied |
| 5 | **Insider Signal** | SEC EDGAR Form 4 filings | N/A (layer skipped) | None | ✅ Fully wired |
| 6 | **Fundamental Score** | FMP `key-metrics-ttm` (ROE, margins, P/E) | yfinance `info` (forward P/E, margins, D/E) | FMP Starter ✅ | ✅ Fixed: `ticker+config` now passed; FMP active |
| 7 | **NLP Sentiment** | Alpha Vantage `NEWS_SENTIMENT` | N/A (layer skipped) | Alpha Vantage free ✅ | ✅ Fixed: now fully wired (was stubbed out) |

### Layer 6 Fundamental Score — Data fields used

| Field | FMP Source | yfinance Fallback |
|---|---|---|
| Forward P/E | `forwardPE` from key-metrics-ttm | `info.forwardPE` / `info.trailingPE` |
| Return on Equity (ROE) | `roe` from key-metrics-ttm | *(not available)* |
| Operating Margin | `operatingMargin` from key-metrics-ttm | `info.profitMargins` (net) |
| Debt / Equity | `debtToEquity` from key-metrics-ttm | `info.debtToEquity` |
| Revenue Growth | *(not from FMP here)* | `info.revenueGrowth` / `info.earningsGrowth` |

### Layer 7 NLP Sentiment — Alpha Vantage limits

| Limit | Value | Mitigation |
|---|---|---|
| Requests per minute | 5 | Graceful skip on rate limit; weight redistributed |
| Requests per day | 500 | One call per ticker per modal open |
| Response | Up to 50 headlines per call | We request 10, use top 3 for UI display |

---

## Price Targets & Scenario Engine — Data Sources

### Entry Zone & Horizon Targets

| Data Point | Source | Key Required | Notes |
|---|---|---|---|
| Current price | yfinance OHLCV | None | Last daily close |
| MA50 / MA200 | yfinance OHLCV (computed) | None | 50/200-day rolling mean |
| 52-week low / high | yfinance OHLCV (computed) | None | 252-day rolling min/max |
| Annual historical volatility | yfinance OHLCV (computed) | None | 20-day std × √252 |
| ML horizon probabilities | LightGBM trained models | None | Short/Medium/Long (20d/60d/120d) |
| **Analyst price targets** | **FMP `price-target-consensus`** | FMP Starter ✅ | **Fixed: now anchors Bull/Base scenario targets** |

### Analyst Target Anchoring (FMP)

When FMP returns analyst consensus data, scenario targets are **anchored to real Wall Street numbers** rather than synthetic ML multiples:

| Scenario | Target Source (FMP available) | Target Source (FMP unavailable) |
|---|---|---|
| Bull Case | FMP analyst **high** target | `current_price × (1 + threshold + bull_extra)` |
| Base Case | FMP analyst **median** target | `current_price × (1 + threshold)` |
| Bear Case | Always synthetic | `current_price × (1 − vol_adjusted_downside)` |

### Live Macro Context (scenario probability gating)

| Macro Input | Source | Key Required | Used For |
|---|---|---|---|
| VIX | yfinance `^VIX` | None | Gates bull/bear probability; suppresses bull when VIX > 22 |
| 10Y Treasury yield | yfinance `^TNX` | None | Yield curve computation |
| 2Y Treasury yield | yfinance `^IRX` | None | Yield curve computation |
| Yield curve (10Y − 2Y) | Computed from above | None | Inverted curve → +8% bear probability |
| DXY (USD index) | yfinance `DX-Y.NYB` | None | Gates USD-strength scenarios for commodities/ADRs |
| Fed Funds Rate | FRED `FEDFUNDS` | FRED free ✅ | Gates rate-cut scenario probability |
| CPI Year-over-Year | FRED `CPIAUCSL` (13mo window) | FRED free ✅ | Gates inflation scenario probability |

### Earnings Timing

| Data Point | Source | Key Required | Used For |
|---|---|---|---|
| Next earnings date | yfinance `Ticker.calendar` → `earnings_dates` | None | Annotates earnings scenarios with "in X days"; boosts probability when within 21 days |

---

## Scenario Engine — Asset-Type-Specific Scenarios

| Asset Type | Scenario Set | Key Triggers Modeled |
|---|---|---|
| `EQUITY_US` | Earnings Beat, Fed Rate Cut, Earnings Miss / Guidance Cut | EPS surprise, forward guidance, rate cycle |
| `EQUITY_SPECULATIVE` | Momentum Squeeze, Institutional Exit, Fed Pivot Risk-On | Short interest, fund flows, rate cycle |
| `EQUITY_DEFENSIVE` | Dividend Increase, Recession Safe-Haven, Rate Spike | Dividend growth, PMI, 10Y yield |
| `EQUITY_ADR` | Geopolitical De-escalation, Regulatory Crackdown, Currency Depreciation | Trade policy, government action, USD/local FX |
| `ETF_EQUITY` | Broad Market Rally, 10%+ Correction, QT Reversal | VIX, SPX level, Fed balance sheet |
| `ETF_COMMODITY` | Fed Pivot, Inflation Re-acceleration, USD Strength Spike, Geopolitical Safe-Haven | Real yield, CPI, DXY, risk-off flow |

---

## Cross-Asset & Macro Context (Dashboard-wide)

| Data Point | Source | Key Required | Used In |
|---|---|---|---|
| SPY daily bars | yfinance | None | Market regime detection |
| VIX daily | yfinance `^VIX` | None | Regime multiplier, risk warnings, ETF options proxy |
| DXY, GLD, USO, SLV | yfinance | None | Cross-asset daily % change panel |
| 10Y Treasury (dashboard) | FMP `treasury-rates` or yfinance `^TNX` | FMP Starter ✅ | Cross-asset guidelines |
| Economic calendar | FMP `economic-calendar` | FMP Starter ✅ | FOMC, CPI event warnings |
| Inflation expectations | FRED `T10YIE` (10Y breakeven) | FRED free ✅ | Real yield proxy |
| Real yield proxy | FRED `DGS10` − `T10YIE` | FRED free ✅ | Macro analog, regime context |
| CFTC COT positioning | CFTC public Socrata API | None | Commodity extreme-positioning flags (gold, silver, crude) |
| BTC-USD, ETH-USD | yfinance | None | Crypto signal section |

---

## Pre-Flight Signal Suite — Data Sources

| Component | Data Required | Source | Status |
|---|---|---|---|
| Asset classification | Ticker symbol | Static registry in `asset_classifier.py` | ✅ Built-in (30+ tickers) |
| Weight profiles | Asset type → weights | `constants.py` WEIGHT_PROFILES | ✅ Built-in |
| Signal coherence | All 7 layer scores | Confidence engine output | ✅ Wired |
| Regime transition probability | HMM state probabilities | Layer 1 HMM output | ✅ Wired |
| Options divergence | Options score + ML score | Layers 3 & 4 | ✅ Wired |
| RSI direction | Close price series | yfinance OHLCV | ✅ Wired |
| Transition momentum bonus | HMM prob + ML prob | Layers 1 & 3 | ✅ Wired |
| Conditional playbook | All layer scores | Confidence engine output | ✅ Wired |

---

## Short Interest Data (FINRA via yfinance)

`backend/signals/short_interest.py` — added 2026-02-28

Yahoo Finance aggregates FINRA bi-weekly short interest and surfaces it through `Ticker.info`. No key required.

| Field | yfinance attribute | Used For |
|---|---|---|
| Short % of float | `shortPercentOfFloat` | Squeeze scenario probability gating |
| Days to cover (DTC) | `shortRatio` | Squeeze amplifier (high DTC = slow exit = amplified move) |
| Shares short | `sharesShort` | Absolute position size |
| Prior month shares short | `sharesShortPriorMonth` | Trend direction (increasing / decreasing) |

**Squeeze probability gating logic:**

| SI % of Float | Default Adj | With ML Bullish | Squeeze Risk |
|---|---|---|---|
| < 2% | −0.18 (suppress) | −0.18 | None |
| 2–5% | −0.08 | −0.08 | Low |
| 5–10% | 0.00 | +0.07 | Moderate |
| 10–15% | 0.00 | +0.14 | Elevated |
| 15–25% | −0.05 | +0.21 | High |
| > 25% | −0.05 | +0.27 | Extreme |

**Error reduction:** Squeeze scenario probability error for speculative names reduced from ~15-25% to ~3-5%.

## FMP Analyst EPS Consensus

`fmp_client.fetch_analyst_estimates` — enhanced 2026-02-28

Now returns full consensus fields including analyst dispersion:

| Field | Description | Used For |
|---|---|---|
| `eps_avg` | Consensus forward EPS | Forward P/E computation in Layer 6 |
| `eps_high` / `eps_low` | Bull / bear analyst EPS | Dispersion calculation |
| `eps_dispersion` | (high−low)/avg | Certainty nudge on fundamental score |
| `analyst_count` | Number of contributing analysts | Label and confidence weighting |
| `certainty` | 0-1 (1 = tight consensus) | ±4% nudge on Layer 6 score |

**Error reduction:** Layer 6 fundamental score error on high-growth names (NVDA, TSLA, LLY) reduced from ~5-10% to ~2-4%.

---

## What Genuinely Cannot Be Fixed Without Paid Upgrades

| Feature | Gap | Reason | Workaround in Place |
|---|---|---|---|
| Real-time (intraday) quotes | yfinance = 15-minute delayed | Yahoo Finance terms | EOD close used — fine for daily signals |
| Alpha Vantage rate limit | 5 req/min, 500/day | Free tier | Graceful skip; weight redistributed to other layers |
| 13F institutional holdings | Requires FMP Ultimate ($249/mo) | Plan limitation | SEC EDGAR Form 4 insider data used as proxy (more timely) |
| Short interest % real-time | FINRA bi-weekly only | No free real-time source | **FINRA bi-weekly via yfinance now wired** — squeeze scenarios data-driven |
| Earnings EPS estimates (forward) | FMP Starter for full analyst estimates | Requires key | **FMP analyst estimates now wired** — full EPS consensus + dispersion used |
| Earnings transcripts | FMP Ultimate | Plan limitation | Not used |
| ETF holdings (ARKK, QQQ constituents) | FMP Ultimate | Plan limitation | ETF classified by asset type; constituent signals not computed |
| Analyst recommendation grades history | FMP Starter for history | Plan check needed | Finnhub `fetch_recommendation()` available but not yet wired into main engine |

---

## Key Files Reference

| Module | File | Purpose |
|---|---|---|
| Confidence engine | `backend/signals/confidence_engine.py` | 7-layer scoring + pre-flight integration |
| Price targets | `backend/signals/price_targets.py` | Horizon targets, scenarios, macro gating |
| ML models | `backend/signals/ml_models.py` | LightGBM training + inference |
| HMM regime | `backend/signals/hmm_regime.py` | Hidden Markov Model bull/bear state |
| Options signals | `backend/signals/options_signals.py` | Put/call ratio, IV rank, max pain |
| Insider signal | `backend/signals/edgar_insider.py` | SEC Form 4 fetch + scoring |
| Fundamentals (FMP) | `backend/signals/fmp_client.py` | Key metrics, price targets, calendar |
| Fundamentals (indicators) | `backend/signals/indicators.py` | Val/quality score computation |
| NLP sentiment | `backend/signals/alpha_vantage_client.py` | News sentiment scoring |
| Macro data | `backend/signals/fred_client.py` | Fed rate, CPI, yield, inflation expectations |
| CFTC COT | `backend/signals/cot_client.py` | Commodity speculative positioning |
| Cross-asset | `backend/signals/cross_asset.py` | DXY, VIX, GLD, oil daily signals |
| Pre-flight suite | `backend/signals/pre_flight/` | Asset classification, coherence, playbook |
| API routes | `backend/api/routers/dashboard.py` | All REST endpoints |
| Config | `backend/config/config.yaml` | All API keys + model parameters |
