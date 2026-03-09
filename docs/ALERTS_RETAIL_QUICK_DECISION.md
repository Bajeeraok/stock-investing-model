# Alerts for Retail Traders/Investors — Quick Decision Guide

This doc lists **alert types that help retail traders/investors take quick decisions**, and how they map to the [refactor alert strategy](#refactor-coverage) (buy/sell + regime + option flow, ST/MT/LT).

---

## 1. What Retail Needs for Quick Decisions

Quick decisions mean: **minimal interpretation**, **one clear action**, and **price + timeframe** when relevant.

| Category | Alert idea | Why it helps |
|----------|------------|--------------|
| **Action** | BUY / ADD — with entry zone and “when to act” | “Add NVDA in $X–$Y when RSI &lt; 35” = one decision. |
| **Action** | TRIM / SELL — with price level and reason | “Consider trim at $Z” or “Reassess above $Z” = clear exit/trim. |
| **Action** | HOLD / WAIT — with next trigger | “Hold; add on dip to MA50 ($X)” = no action now, clear next step. |
| **Regime** | Regime change (e.g. BULL → BEAR) | “Market flipped — review positions” = re-evaluate without parsing data. |
| **Price level** | Price entered your **entry zone** | “GOOGL in buy zone $296–$302” = model says you can add now. |
| **Price level** | **Stop / invalidation** hit | “Price below $X — thesis invalidated” = exit or reduce. |
| **Price level** | **Target** hit | “Target $X reached — consider taking profit” = optional take-profit nudge. |
| **Earnings** | Earnings in X days (1–7) | “Earnings in 3 days — reduce size or hedge” = binary risk reminder. |
| **Options** | High IV / IV crush / unusual flow | “IV extreme — covered call opportunity” or “Unusual call flow + regime up” = options/conviction cue. |
| **Model gate** | ML probability crossed threshold | “ML prob &gt; 25% — model now supports add” = timing for entry. |
| **Macro** | Risk-off / risk-on shift | “VIX &gt; 25 — reduce new buys” = portfolio-level caution. |

---

## 2. Refactor Strategy Coverage

Our earlier refactor recommendations were:

- **Primary:** BUY/ADD/TRIM/SELL + regime change; option flow as confirmation/filter.
- **ST:** Tactical BUY/ADD/TRIM/SELL; regime as gate; flow as filter.
- **MT:** ADD/TRIM driven by regime change; flow as confirmation.
- **LT:** Fewer alerts; “review thesis” on regime change.
- **Regime change** as first-class trigger.
- **Option flow** for OPTIONS_FLOW_SPIKE and to confirm/filter buy/sell.

Mapping **retail quick-decision needs** to that strategy:

| Retail need | In refactor? | Notes |
|-------------|--------------|--------|
| BUY/ADD with entry + “when to act” | ✅ Yes | Core: BUY/ADD alerts; horizon logic already has entry zone + trigger_buy. |
| TRIM/SELL with price + reason | ✅ Yes | TRIM/SELL + “Reassess above $X” (confidence summary). |
| HOLD/WAIT with next trigger | ✅ Yes | HOLD/WATCH + regime/MA50 in action summary. |
| Regime change | ✅ Yes | REGIME_CHANGE as first-class trigger; “re-evaluate” on flip. |
| Price entered **entry zone** | ⚠️ Partial | We have entry zones and trigger_buy text; **no dedicated “price in zone” alert** that fires when price crosses into zone. |
| **Stop / invalidation** hit | ❌ No | Not called out; need “alert when price &lt; invalidation (or stop)”. |
| **Target** hit | ❌ No | Not called out; optional “target reached” alert. |
| Earnings in X days | ⚠️ Partial | ER_LOTTO / ER_IV_CRUSH exist; **“Earnings in 3/5/7 days”** as a simple countdown alert not explicit. |
| High IV / flow spike | ✅ Yes | OPTIONS_FLOW_SPIKE; IV extreme; flow as confirmation for buy/sell. |
| ML prob crossed threshold | ⚠️ Partial | Regime + ML in logic; **“ML prob crossed 25%”** as a distinct alert type not explicit. |
| Macro risk-off/on | ✅ Yes | MACRO_RISK_OFF / MACRO_RISK_ON. |

So we **did not** fully incorporate:

1. **Entry-zone entered** — “Price in your buy zone” alert.
2. **Stop / invalidation hit** — “Price below $X — exit/trim.”
3. **Target hit** (optional) — “Target $X reached.”
4. **Earnings countdown** — “Earnings in X days” (1–7) as a simple, standalone alert.
5. **ML threshold cross** — “ML prob crossed 25% — consider add” (or similar).

---

## 3. Additions to the Refactor Strategy (Retail Quick Decision)

To align the refactor with **all** useful retail quick-decision alerts, add the following to the strategy.

### 3.1 Price-level alerts (retail-friendly)

- **ENTRY_ZONE_ENTERED**  
  Fire when **current price is inside** the model’s **entry zone** for that horizon (ST/MT/LT) for a watchlist ticker.  
  Message: *“{Ticker} in {Short|Medium|Long} entry zone $X–$Y. {Trigger_buy one-liner or ‘Consider adding.’}”*

- **STOP_HIT**  
  Fire when **price &lt; invalidation level** (or stop) from the same model (e.g. confidence/watch_levels or horizon stop_loss).  
  Message: *“{Ticker} below stop $X — consider exit or trim.”*

- **TARGET_HIT** (optional)  
  Fire when **price ≥ target** (e.g. horizon target or LT fair value).  
  Message: *“{Ticker} reached target $X — consider taking profit.”*

Implementation note: These need **last price vs last alert state** (e.g. “was above zone, now in zone”) to avoid spam; cooldowns and “only when crossing into zone” logic.

### 3.2 Earnings countdown

- **EARNINGS_SOON**  
  Fire for watchlist tickers when **days_to_earnings in [1, 3, 5, 7]** (configurable).  
  Message: *“{Ticker} earnings in {X} days — reduce size or wait for reaction.”*  
  Keeps ER_LOTTO/ER_IV_CRUSH for options/IV; this is a simple, actionable reminder.

### 3.3 Model threshold cross

- **ML_PROB_CROSSED**  
  Fire when **ML probability crosses a threshold** (e.g. 25% or 40%) in the direction that supports the action (e.g. cross above 25% for ADD).  
  Message: *“{Ticker} ML prob now {X}% (crossed {threshold}%) — model supports add.”*  
  Optional: same for “crossed below” for TRIM.  
  Requires storing **previous ML prob** per ticker and comparing on each scan.

### 3.4 One-line plain English

- Every alert **payload** should include a **single-sentence recommendation** in plain English: action + price (if any) + timeframe (if any).  
  Example: *“Add on pullback to $296–$302 (Short-term).”* or *“Trim — reassess above $320.”*  
  This is already aligned with the “action + price + timeline in plain English” goal for ticker detail and should extend to alerts.

---

## 4. Summary Checklist for Refactor

When refactoring alerts, ensure the system supports:

| # | Alert / behavior | Purpose for retail |
|---|------------------|--------------------|
| 1 | BUY/ADD with entry zone + trigger_buy | Core add decision. |
| 2 | TRIM/SELL with price + reason | Core trim/exit decision. |
| 3 | HOLD/WAIT with next trigger | No action now; clear next step. |
| 4 | REGIME_CHANGE | Re-evaluate book. |
| 5 | **ENTRY_ZONE_ENTERED** | “Price in zone — you can add.” |
| 6 | **STOP_HIT** | “Thesis broken — exit/trim.” |
| 7 | **TARGET_HIT** (optional) | “Take profit.” |
| 8 | **EARNINGS_SOON** (X days) | Binary risk reminder. |
| 9 | **ML_PROB_CROSSED** (e.g. 25%) | Timing for add/trim. |
| 10 | OPTIONS_FLOW_SPIKE + regime | Unusual activity + context. |
| 11 | MACRO_RISK_OFF / RISK_ON | Portfolio-level caution. |
| 12 | Every alert: one-line plain English | Quick decision without parsing. |

Items **5–9** are the ones that were **not** fully incorporated in the original refactor; adding them makes the refactor strategy complete for retail quick decisions.
