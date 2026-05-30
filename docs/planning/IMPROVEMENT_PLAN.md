# Investing Cockpit – Improvement Plan

Based on UX feedback: make "What changed" actionable, tie notes to rules, add risk sizing, surface concentrations, and improve event awareness.

---

## 1. Make "What changed" do real work

### Current state
- `what_changed()` in `backend/behavior/what_changed.py` compares prev vs curr and returns list of strings.
- **Bug**: Dashboard calls `save_last_run(results)` then `load_last_run()` → compares new vs new. Must load previous run **before** saving.
- Outputs: "MA50 crossed below MA20", "Score down 15 pts", "Regime UP -> NEUTRAL" – good start but no single-line summary.

### Required changes

| Task | Location | Description |
|------|----------|-------------|
| **1.1** | `dashboard.py` | Load `last_run` **before** `save_last_run(results)`. Use pre-save `last_run` for `what_changed`. |
| **1.2** | `what_changed.py` | Add `summary` field: one compact line per ticker, e.g. `"MSFT: 84 → 72 (UP→NEUTRAL): trend weakened after break below 50D MA"`. |
| **1.3** | `what_changed.py` | Include regime + score in summary; derive brief reason from MA/RSI/MACD changes when available. |
| **1.4** | API response | Extend `what_changed` items: `{ ticker, changes[], summary }`. |
| **1.5** | `WhatChanged.tsx` | Show `summary` as primary line; keep `changes` as expandable detail. |

### Example output
```
MSFT: 84 → 72 (UP→NEUTRAL): Score down 12 pts, MA50 crossed below MA20
GLD: 55 → 71 (NEUTRAL→UP): RSI recovered from oversold, price back above MA50
```

---

## 2. Tie notes to clear rules

### Current state
- Short/Medium/Long: rule-driven in `indicators.py` via `_sugg(score, buy=65, sell=35)`.
- Earnings: rule-driven when `days_until <= days_warn` (default 14).
- Rules are implicit in code, not documented or configurable.

### Required changes

| Task | Location | Description |
|------|----------|-------------|
| **2.1** | `config.yaml` | Add `rules` section with thresholds (buy_min, sell_max, earnings_days_warn, etc.). |
| **2.2** | `config/tooltips.yaml` or new `rules.yaml` | Document rule logic: "LT score ≥ 70 + regime UP → HOLD/ADD", etc. |
| **2.3** | `indicators.py` | Ensure all suggestion logic uses config thresholds; no hardcoded 65/35 in `_sugg` if config provides them. |
| **2.4** | README / config | Add "Rule logic" section: `score ≥ buy_min → ADD`, `score ≤ sell_max → TRIM`, `earnings ≤ 5 days → append note`. |

### Rule summary (to document)
- LT score ≥ 70 and regime UP → "HOLD/ADD for medium/long"
- LT score 40–70 → "HOLD/NEUTRAL"
- LT score < 40 or regime DOWN → "CONSIDER TRIM / AVOID NEW"
- Earnings ≤ 5 days → append "Earnings in X days – consider waiting"

---

## 3. Add simple risk + position sizing

### Current state
- No position sizing or risk-based guidance.

### Required changes

| Task | Location | Description |
|------|----------|-------------|
| **3.1** | `indicators.py` or `portfolio/doctor.py` | Add `suggested_position_size(close, risk_pct=1, stop_pct=10, portfolio_value)` → returns dollar size and share count. |
| **3.2** | API | Add `suggested_position_size` (or `risk_sizing`) to each signal: `{ size_dollars, shares, stop_distance_pct }`. |
| **3.3** | Config | Add `risk_sizing: { risk_pct: 1, default_stop_pct: 10 }`; use portfolio total_value for calculation. |
| **3.4** | `SignalsTable.tsx` | Add expandable row or tooltip: "At 1% risk and 10% stop: $4,000 (~58 shares)". |

### Formula
- `position_size = portfolio_value * (risk_pct / 100) / (stop_pct / 100)`
- `shares = position_size / close`

---

## 4. Highlight portfolio concentrations

### Current state
- `portfolio_report` returns `largest_position`, `concentration_alert`.
- `PortfolioSummary` shows "Largest" with ticker and %, plus "Concentration alert" if any exceed threshold.
- Top-3 combined % is not computed.

### Required changes

| Task | Location | Description |
|------|----------|-------------|
| **4.1** | `portfolio/doctor.py` | Add `top3_pct` (sum of top 3 holdings by value) to report. |
| **4.2** | `portfolio/doctor.py` | In `largest_position`, include `score` and `regime` when available. |
| **4.3** | API | Include `top3_pct` in portfolio report. |
| **4.4** | `PortfolioSummary.tsx` | Add line: "Top 3 = X% of portfolio". |
| **4.5** | `PortfolioSummary.tsx` | Expand "Largest" to: "Largest: XYZ – 18%, score 52 (NEUTRAL)" when data available. |

---

## 5. Event awareness surfaced clearly

### Current state
- "Earnings in X days" in Notes column.
- No visual de-emphasis or event-risk summary.

### Required changes

| Task | Location | Description |
|------|----------|-------------|
| **5.1** | API | Add `earnings_risk_count`: count of holdings with earnings in next 7 days. |
| **5.2** | Dashboard header or alerts | Add banner/tag: "3 holdings with earnings in next week" when count > 0. |
| **5.3** | `SignalsTable.tsx` | Grey out row or add caution icon when `earnings_note` present and `days_until <= 7`. |
| **5.4** | Config | Add `earnings_caution_days: 7` (or reuse `days_warning`). |

---

## 6. Medium-term enhancements (later)

| Task | Description |
|------|-------------|
| **6.1** | Filters/sorts: by score, regime, short-term signal, upcoming events. |
| **6.2** | Exclusion rules: "Don't buy ST_BUY if LT regime is DOWN"; "Don't add if position > X%"; label such rows. |
| **6.3** | Optional config: `exclusion_rules: { no_buy_if_lt_down: true, max_position_pct: 15 }`. |

---

## Implementation order

1. **Fix "What changed" bug** (1.1) – quick, high impact.
2. **Enrich "What changed" summaries** (1.2–1.5).
3. **Portfolio concentration** (4.1–4.5) – data exists, mostly UI.
4. **Event awareness** (5.1–5.4) – low effort.
5. **Risk sizing** (3.1–3.4) – new logic.
6. **Rule documentation** (2.1–2.4) – config + docs.

---

## Sample JSON (for rule design)

Example signal object from backend:
```json
{
  "ticker": "MSFT",
  "close": 420.50,
  "composite_buy": 72,
  "rsi": 58,
  "regime": "UP",
  "signal": "BUY",
  "short_suggestion": "HOLD/ADD",
  "medium_suggestion": "HOLD/ADD",
  "long_suggestion": "HOLD/ADD",
  "ma20": 415.2,
  "ma50": 408.1,
  "macd_hist": 0.15,
  "earnings_note": "Earnings in 4 days"
}
```

Rules can be expressed as:
- `signal` = f(composite_buy, buy_min, sell_max)
- `short/medium/long_suggestion` = f(short/medium/long_term score, buy, sell)
- `earnings_note` = present when days_until ≤ days_warning
