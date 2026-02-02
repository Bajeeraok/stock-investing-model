# Future Features & Chatbot Assessment

## Additional indicators/features for retail investors

### Cross-asset, commodities & macro (daily impact)

| Feature | Question answered | Implementation |
|--------|--------------------|----------------|
| **Commodities (DXY, oil, gold)** | "How are USD, oil, gold moving today?" | Fetch DXY, WTI/CL, GLD daily; show % change vs prior close. Flag when DXY up + oil down (risk-off). |
| **Other asset classes (rates, credit)** | "What's the 10Y yield doing?" | 10Y Treasury yield; high yields often pressure growth stocks. |
| **Equity–commodity correlation** | "Does NVDA move with oil/gold?" | Rolling correlation ticker vs GLD, USO, DXY; show on ticker detail. |
| **Cross-asset regime** | "Risk-on or risk-off today?" | Composite: SPY + DXY + oil + VIX; label day as risk-on/off. |

### Crypto section (BTC, ETH)

| Feature | Question answered | Implementation |
|--------|--------------------|----------------|
| **BTC, ETH daily** | "How is crypto moving?" | yfinance BTC-USD, ETH-USD; same signals (score, regime, RSI) as equities. |
| **Crypto vs equities** | "BTC leading or lagging SPY?" | Correlation BTC vs SPY; show regime alignment. |
| **Crypto in cross-asset** | "Risk-on: equities + crypto up?" | Include BTC in risk-on/off composite. |
| **Crypto in portfolio** | "Hold BTC/ETH in portfolio doctor?" | Optional crypto watchlist; include in portfolio if held. |

### Whale trades & unusual activity

| Feature | Question answered | Implementation |
|--------|--------------------|----------------|
| **Whale trades (13F, large blocks)** | "Are institutions buying/selling?" | 13F filings (quarterly) or paid APIs (Unusual Whales, Quiver). Large block prints via L2/tape if available. |
| **Unusual options flow** | "Unusual call/put activity?" | Paid APIs (Unusual Whales, FlowAlgo) or free aggregate (CBOE put/call, VIX term structure). |
| **Volume vs average** | "Unusual volume today?" | Today vs 20d avg volume; flag > 2x. Already in medium-impact; elevate. |
| **Dark pool / lit ratio** | "Where is volume trading?" | Dark pool % of volume (if data available). |

### Geopolitical & news

| Feature | Question answered | Implementation |
|--------|--------------------|----------------|
| **Geopolitical headlines** | "What macro/geo risks today?" | News API (NewsAPI, Benzinga) filtered for geo keywords; daily digest. |
| **Sector/region impact** | "How does China/EU policy affect my holdings?" | Map tickers to regions; flag when region-specific news. |
| **Event calendar** | "Fed, CPI, jobs this week?" | Economic calendar (TradingEconomics, FMP); show next 7 days. |

### Correlation for equities/stocks (expanded)

| Feature | Question answered | Implementation |
|--------|--------------------|----------------|
| **Pairwise correlation** | "Do my holdings move together?" | Rolling 1y correlation matrix; flag > 0.8 (redundant risk). |
| **Ticker vs benchmarks** | "NVDA vs SPY, QQQ, XLK correlation?" | Correlation vs SPY, sector ETF, peers; in ticker detail. |
| **Correlation regime** | "Are correlations rising (crisis)?" | Average pairwise correlation of portfolio; rising = diversification failing. |

---

### High-impact (answer common questions)

| Feature | Question answered | Implementation |
|--------|--------------------|----------------|
| **Drawdown / max DD** | "How much could I lose from peak?" | Track 52w high vs current; show % below high. Add to ticker detail. |
| **Volatility (ATR or 20d std)** | "Is this stock too wild for my risk?" | 14-day ATR or 20d rolling std; normalize vs SPY. |
| **Dividend yield + ex-date** | "When's my next dividend?" | yfinance `dividends`; show yield and next ex-date. |
| **Beta vs SPY** | "How does this move vs the market?" | 1y rolling beta; helps size and correlation. |
| **Sector allocation pie** | "Am I too concentrated in tech?" | Sum portfolio % by sector; show pie or bar. |
| **YTD / 1Y return** | "How is my portfolio doing this year?" | Already have returns; add portfolio-level YTD. |
| **Correlation matrix** | "Do my holdings move together?" | Pairwise return correlation; flag > 0.8. |

### Medium-impact

| Feature | Question answered |
|--------|--------------------|
| **P/E, P/S from yfinance** | "Is it expensive?" |
| **52w high/low** | "Where are we in the range?" |
| **Volume vs average** | "Unusual activity?" (see also Whale trades & unusual activity) |
| **Sector rotation view** | "Which sectors are leading?" (XLK, XLF, etc. vs SPY) |
| **Tax lot tracker** | "Which lots to sell for tax loss?" (needs cost basis per lot) |

### Lower effort, high value

- **"Why is my score down?"** – One-click explanation: "RSI overbought + MA50 crossed below MA20."
- **Filters/sorts** – By score, regime, earnings date, sector.
- **Exclusion rules** – "Don't show BUY if LT regime DOWN" – config flag.

---

### Other inputs for better daily signals, portfolio doctor, long-term opportunities

| Input | Where it helps | Implementation |
|-------|----------------|----------------|
| **Market breadth** | Daily signals | Advance/decline ratio, % stocks above 50d MA (SPY universe). Bearish breadth = lower confidence. |
| **VIX level & term structure** | Daily signals, risk regime | VIX > 20 caution; VIX contango vs backwardation. |
| **Sector momentum** | Long-term opportunities | Which sectors outperforming 3m/6m; tilt opportunities toward leaders. |
| **Earnings surprise history** | Portfolio doctor | Beat/miss rate; flag stocks with repeated misses. |
| **Insider activity** | Long-term opportunities | Net buys vs sells (SEC Form 4); filter or rank. |
| **Analyst revisions** | Long-term opportunities | Upgrades/downgrades; estimate revisions (FMP, etc.). |
| **Fund flows** | Cross-asset | ETF inflows/outflows (QQQ, SPY, sector ETFs). |
| **Sentiment (social/options)** | Daily signals | Put/call ratio; retail sentiment (e.g. StockTwits) if available. |

---

### 2026 best tickers (forward-looking with confidence & learning)

| Feature | Description | Implementation |
|--------|-------------|----------------|
| **2026 best tickers** | Ranked list of tickers likely to perform well in 2026 with confidence score (0–100). | Seed from: LT score, regime, sector momentum, analyst trends; score = weighted combo. |
| **Confidence score** | How sure we are about each pick. | Based on: data quality, backtest hit rate, consistency of signals, breadth of support. |
| **Daily absorption** | Keep tweaking by absorbing daily market stats. | EOD: update each ticker's score using latest price, regime, earnings, sector relative strength. |
| **Feedback loop** | Improve picks over time. | Backtest: when we said "2026 pick" at date T, what was 1m/3m forward return? Adjust weights. |
| **Versioning** | Track how picks change. | Store weekly/monthly snapshots; show "added X, removed Y, confidence changed." |

**Suggested flow**
1. **Seed list**: Top LT scores + regime UP + sector leaders; exclude earnings within 2 weeks.
2. **Confidence**: Higher when score stable, sector strong, no negative catalysts.
3. **Daily update**: Recompute scores; rank by confidence × LT score; keep top 20–30.
4. **Monthly review**: Compare actual vs predicted; tune weights (e.g. sector momentum weight).
5. **Store in EOD**: Save 2026 picks snapshot with confidence; backtest later.

---

## Chatbot for natural-language questions

### Feasibility: **Yes, with clear scope**

A chatbot that answers ad-hoc investment questions is feasible. Two main approaches:

### Option A: Rule-based / retrieval (simpler, no LLM)

- **How**: Map intents to backend queries. Examples:
  - "What's my biggest holding?" → portfolio report largest_position
  - "Why did MSFT drop?" → what_changed + ticker detail
  - "Which stocks have earnings soon?" → filter signals by earnings_note
  - "What's the score for NVDA?" → signals lookup
- **Pros**: Fast, no API cost, deterministic, works offline
- **Cons**: Limited to predefined questions; needs good intent parsing or keywords

### Option B: LLM-based (OpenAI, Anthropic, local)

- **How**: Send question + context (portfolio summary, signals, watchlist) to an LLM. LLM answers using that context.
- **Pros**: Natural language, flexible questions, can explain and summarize
- **Cons**: API cost, latency, needs safeguards (no trading advice disclaimer), context window limits

### Recommended hybrid

1. **Phase 1 (rule-based)**  
   - Handle top 10–15 questions via intent/keyword matching.  
   - Examples: "biggest position", "why [ticker]", "earnings", "score for X", "what changed", "trim candidates".  

2. **Phase 2 (LLM assist)**  
   - Add an optional LLM for open-ended questions.  
   - Provide structured context (JSON summary of portfolio, signals, what_changed).  
   - Add disclaimer: "For informational use only; not investment advice."

### Chatbot intents (expanded for new categories)

| Intent | Example question | Backend |
|--------|------------------|---------|
| `explain_score_change` | "Why did MSFT score drop?" | what_changed + ticker detail |
| `earnings_upcoming` | "Which holdings have earnings soon?" | Filter signals by earnings_note |
| `biggest_holding` | "What's my biggest position?" | portfolio_report largest_position |
| `whale_activity` | "Any whale buys in my watchlist?" | Whale trades / 13F service |
| `unusual_volume` | "Unusual activity today?" | Volume vs 20d avg; flag > 2x |
| `cross_asset` | "How are gold and oil moving?" | Commodities / DXY daily fetch |
| `correlation` | "How correlated are my holdings?" | Correlation matrix |
| `geo_news` | "Geopolitical risks today?" | News API filtered for geo |
| `risk_regime` | "Risk-on or risk-off today?" | Cross-asset regime composite |
| `crypto` | "How is BTC/ETH doing?" | Crypto section (BTC-USD, ETH-USD) |
| `best_2026` | "What are your 2026 picks?" | 2026 best tickers + confidence |

### Technical sketch

```
User: "Why did my MSFT score drop?"
  → Intent: explain_score_change(ticker=MSFT)
  → Backend: what_changed(prev, curr) for MSFT
  → Response: "MSFT: 84 → 72 (UP→NEUTRAL): Score down 12 pts, trend weakened after break below 50D MA"

User: "Which of my holdings have earnings in the next week?"
  → Intent: earnings_upcoming(days=7)
  → Backend: filter signals where earnings_note matches
  → Response: "3 holdings: AAPL (4 days), MSFT (6 days), NVDA (2 days)"

User: "Should I add to NVDA?"
  → Intent: open_ended_advice (use LLM with context)
  → Context: NVDA score, regime, thesis, support_level, earnings
  → LLM: Summarize without giving explicit buy/sell recommendation
```

### Implementation outline

1. **Backend**: Add `POST /api/chat` that:
   - Accepts `{ "question": "..." }`
   - Runs intent detection (keyword/regex or small classifier)
   - Calls the right service (portfolio_report, what_changed, signals, etc.)
   - Returns `{ "answer": "...", "sources": [...] }`

2. **Frontend**: Chat panel or floating widget:
   - Input box + send button
   - Stream or show answer with optional "sources" expand

3. **Optional LLM**: If intent = "open_ended", call OpenAI/Anthropic with:
   - System: "You are an investment research assistant. Use only the provided context. Do not give explicit buy/sell advice."
   - User: question + JSON context

---

## Summary & roadmap

| Category | Recommendation | Effort |
|----------|----------------|--------|
| **Crypto (BTC, ETH)** | Dedicated section; same signals as equities; include in cross-asset | ~0.5–1 day |
| **Indicators** | Drawdown, volatility, dividend, beta, sector allocation | ~0.5 day each |
| **Cross-asset & commodities** | DXY, oil, gold daily; equity–commodity correlation; risk-on/off regime | ~1–2 days |
| **Other inputs** | Market breadth, VIX, sector momentum, insider activity, analyst revisions | ~0.5–2 days each |
| **2026 best tickers** | Forward-looking picks with confidence; daily absorption; feedback loop | ~2–3 days |
| **Whale trades & unusual activity** | Volume vs avg; whale/13F (quarterly); options flow (paid API) | ~0.5–2 days |
| **Geopolitical news** | News API + geo filter; economic calendar | ~1 day + API |
| **Correlation** | Pairwise portfolio; ticker vs benchmarks; correlation regime | ~0.5–1 day |
| **Chatbot** | Rule-based for top questions; add LLM for open-ended | 1–3 days |

### Prioritization

1. **Quick wins**: Crypto section (BTC, ETH), volume vs avg, DXY/oil/gold daily, pairwise correlation.
2. **Medium**: 2026 best tickers (v1 with confidence), economic calendar, risk-on/off composite, market breadth, VIX.
3. **Learning loop**: Daily absorption for 2026 picks; EOD snapshots; monthly backtest to tune weights.
4. **Paid / external**: Whale trades (13F/Unusual Whales), options flow, news API, analyst revisions.
5. **Chatbot**: Wire intents (`crypto`, `best_2026`, `whale_activity`, `cross_asset`, etc.) as data becomes available.
