# Stock Investing Model: Analysis, Recommendations & Implementation Strategy

## 1. My Analysis of What You Have

The architecture you’ve been given is **sound and buildable**. It correctly separates:

- **Data** (prices, fundamentals, your holdings/watchlist)
- **Signals** (technical + optional fundamental → 0–100 score, regime)
- **Alerts & recommendations** (trend flips, portfolio “doctor,” watchlist suggestions)

For a retail investor doing **long-term core + swing trades** (e.g. SPY/QQQ + GLD/SLV), this fits well. Below is my take on strengths, gaps, and how useful it is for you.

---

## 2. What’s Strong (Keep This)

| Area | Why it helps you |
|------|-------------------|
| **Single composite score (0–100)** | One number to answer “buy vs sell?” without staring at 10 indicators. |
| **Regime labels (UP / NEUTRAL / DOWN)** | Perfect for swing alerts: “GLD flipped from UP to NEUTRAL” is actionable. |
| **Multi-horizon idea** | Short-term (weeks) vs medium-term (months) avoids “chart looks good but valuation is stretched.” |
| **Portfolio-level view** | Most tools are stock-only. Factor/sector tilt + concentration alerts protect you from accidental bets. |
| **Thesis + checklist** | Writing “why I own this” and “what would make me sell” reduces emotional selling and FOMO buying. |
| **Earnings/event calendar** | Reducing score before earnings and flagging “don’t walk in blind” is practical. |
| **Peer / benchmark context** | “Is this expensive vs sector/peers?” reduces overpaying on momentum alone. |

---

## 3. Gaps & Risks (Where to Add Your Own Thinking)

### 3.1 Starter code limitations

- **No handling of missing/incomplete data**: New IPOs, delistings, or API gaps can break `close.iloc[-1]` or produce NaN. You need checks and fallbacks.
- **Trend score is too coarse**: Only three buckets (100 / 50 / 0) lose information. A gradient (e.g. distance of price vs MA50/MA200) gives smoother scores.
- **RSI “score” is symmetric around 50**: For swing trading, oversold (RSI &lt; 30) should boost buy score; overbought (RSI &gt; 70) should reduce it. The current formula doesn’t capture that asymmetry well.
- **No MACD in the snippet**: The outline mentions MACD; the code doesn’t. Add it for crossover and histogram strength.
- **Regime from trend only**: Regime should use composite score (or at least trend + momentum), not just the raw trend bucket, so “UP”/“DOWN” match what you actually trade on.

### 3.2 Behavioral and product

- **Over-trusting the score**: If you treat 75 as “always buy,” you’ll get hurt when the regime shifts. The tool should say “consider buying” and show *reasons*, not “the model says buy.”
- **Alert fatigue**: Too many alerts (every small score change) → you ignore them. Only alert on regime change, large score moves (e.g. ±15), and optional earnings/events.
- **Backtesting before live use**: The outline says “backtest 10+ years”; the code doesn’t. You need a small backtest (even simple: “when score &gt; 70, what was 3‑month forward return?”) before relying on thresholds.

### 3.3 Data and ops

- **yfinance is not reliable for automation**: Rate limits, occasional breakage. Fine for prototyping; for daily runs use a paid EOD source (FMP, Tiingo) or at least retries + logging.
- **No persistence**: The snippet recomputes everything each run. You need to store last run’s regime/score to detect “regime changed” and “score moved a lot.”

---

## 4. Overall Recommendations

### 4.1 For you as a retail investor

1. **Use it as decision support, not autopilot**  
   Score + regime + explanation → you decide. Never auto-trade on score alone.

2. **Start with a small, fixed watchlist**  
   e.g. SPY, QQQ, GLD, SLV + 5–10 stocks. Validate that signals “feel right” and backtest roughly before adding more.

3. **Prioritize portfolio and risk over more indicators**  
   Factor/sector breakdown, max position %, and “what if SPY −20%?” matter more than a 10th technical indicator.

4. **Lock in “thesis + rules” per position**  
   When you add a position, record thesis, horizon, and “I will trim/exit if …”. The system should resurface this when score or regime changes.

5. **One data backbone, then add features**  
   Pick one EOD + fundamentals provider (e.g. FMP or Tiingo), get scores and alerts working, then add earnings, peers, sentiment.

### 4.2 Technical recommendations

- **Improve the composite**:  
  Trend (e.g. 0–40) + momentum/RSI (e.g. −20 to +20) + optional MACD/volume, then normalize to 0–100. Asymmetric RSI: oversold adds to buy score, overbought subtracts.

- **Regime from composite (or trend + momentum)**  
  e.g. UP: composite ≥ 60, DOWN: ≤ 40, else NEUTRAL. Store previous regime to emit “regime changed” alerts.

- **Persistence layer (v1)**  
  SQLite or JSON is enough: last run’s date, per-ticker score and regime. Next run: diff → alerts.

- **Backtest module (simple)**  
  For each date, compute score; bucket (e.g. 0–30, 30–50, 50–70, 70–100); compute forward 1/3/6 month return by bucket. Check that higher score ≈ higher average return (and that 70+ isn’t terrible in drawdowns).

---

## 5. Implementation Strategy (Phased)

### Phase 1 – Core (1–2 weeks): “One score, one regime, for my watchlist”

- **Data**: yfinance (or one EOD API) for daily OHLCV.
- **Signals**: MA20/50/200, RSI(14), optional MACD. Composite 0–100, regime UP/NEUTRAL/DOWN from composite.
- **Output**: Table of ticker, close, score, regime, signal (BUY/HOLD/SELL); optional CSV/JSON.
- **Fix**: NaNs, short history (e.g. &lt; 200 days), and weekends/holidays.
- **Deliverable**: Script you run daily; same watchlist every time.

### Phase 2 – Alerts (≈1 week): “Tell me when something important changes”

- **Persistence**: Store last run’s score and regime per ticker.
- **Alert rules**:  
  - Regime change (UP→NEUTRAL, NEUTRAL→DOWN, etc.).  
  - Score move ≥ 15 points.  
  - Optional: RSI &gt; 70 or &lt; 30.
- **Channel**: Email or Telegram/Discord (one message per day digest or per alert).
- **Deliverable**: Daily job; you get a short alert list only when conditions fire.

### Phase 3 – Portfolio “doctor” (≈1 week): “How healthy is my portfolio?”

- **Input**: Holdings (ticker, quantity, optional cost basis) + watchlist.
- **Per holding**: Current score, regime, suggestion (hold/add / neutral / consider trim).
- **Portfolio-level**: Average score, count in each regime, top concentration (e.g. “largest position 25%”).
- **Optional**: Sector breakdown if you have sector from API or static map.
- **Deliverable**: Portfolio report (text or simple HTML) after each run.

### Phase 4 – Better data & context (ongoing): “Fewer blind spots”

- **Data**: Move to FMP or Tiingo for EOD + fundamentals; keep one source of truth.
- **Earnings**: Pull next earnings date; reduce score or flag “earnings in N days” for that ticker.
- **Peers/benchmark**: For each ticker, show score vs sector ETF or 2–3 peers (when data available).
- **Backtest**: Simple backtest of score vs forward returns; tune bands (e.g. 65/35 instead of 70/30) from your own history.

### Phase 5 – UX and behavior (later): “Stick to my plan”

- **Thesis capture**: When adding to portfolio or watchlist, store “why” and “exit condition.”
- **Nudges**: “You said you’d trim if regime went DOWN; it did” or “Score still strong; don’t sell just because it’s up 20%.”
- **Inline tooltips**: One line per indicator (“50D &gt; 200D: longer-term uptrend; often associated with …”).

---

## 6. How Useful for Retail Investors (Summary)

| Need | How this system helps |
|------|------------------------|
| “Should I buy or sell this?” | One score + regime + short explanation; less chart overload. |
| “Did the trend actually change?” | Regime-change alerts (e.g. golden/death cross, composite bands) instead of noise. |
| “Am I too concentrated?” | Portfolio view + concentration and sector alerts. |
| “What if the market drops?” | Simple scenario (e.g. beta × SPY drop) and risk metrics. |
| “Why did I own this again?” | Thesis + rules; resurface when score/regime changes. |
| “Am I buying a falling knife?” | Score dropping while price falls → “falling knife” nudge. |
| “Am I selling winners too early?” | Score/trend still strong → “trend intact” nudge. |

**Bottom line**: Very useful as a **disciplined, repeatable framework** that combines technical (and later fundamental) signals with portfolio and behavioral guardrails. It’s not an edge by itself—it makes your process clearer and reduces emotional and structural mistakes. That’s where the real value is for a retail investor like you.

---

## 7. Next Steps (Concrete)

1. **This weekend**: Run the improved starter script (see `signals/` in this repo) on SPY, QQQ, GLD, SLV and 2–3 stocks. Inspect scores and regimes; tweak weights so they match your intuition.
2. **Week 2**: Add persistence (e.g. `last_run.json`) and regime-change + big-score-move alerts; one daily run (cron or Task Scheduler).
3. **Week 3**: Add a small portfolio file (ticker, shares); generate portfolio summary and “consider trim” list.
4. **Month 2**: Switch to FMP or Tiingo for at least prices; add earnings dates and optional backtest.
5. **Ongoing**: Add thesis capture and “what changed” explanations when you have time.

If you share your typical holding period (e.g. 6–24 months) and 3–5 tickers you care about most, the next iteration can tune indicator weights and alert thresholds for your style.
