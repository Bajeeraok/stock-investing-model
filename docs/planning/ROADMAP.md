# Thrive Alpha – Implementation Roadmap

This document tracks the implementation plan and verification checklist. Use it to resume work and verify each item.

---

## Priority order (agreed)

| # | Feature | Status | Notes |
|---|---------|--------|-------|
| 1 | **#3 Performance vs benchmark** | ✅ Done | Portfolio vs SPY/QQQ (1m, 3m, 6m, 1y) |
| 2 | **#4 Forward tracking** | ✅ Done | "What we said vs what happened" |
| 3 | #1 Alerts | Not started | Email/Telegram for confidence, regime, opportunities |
| 4 | LLM Chat | Not started | Structured context + OpenAI/Claude |
| 5 | #2 Mobile-friendly UI | Not started | Responsive layout |
| 6 | #5 Execution assist | Not started | Broker integration / order prefilling |

---

## #3: Performance vs benchmark

**Goal:** Show portfolio total return vs SPY and QQQ over 1m, 3m, 6m, 1y. Answer: "How did I do vs the market?"

### Scope

- **Periods:** 1m, 3m, 6m, 1y (trading days: ~21, ~63, ~126, ~252)
- **Portfolio:** Value today vs value at start of each period (holdings × close)
- **Benchmarks:** SPY, QQQ
- **Output:** Portfolio +X%, SPY +Y%, QQQ +Z%, vs SPY (X−Y), vs QQQ (X−Z)

### Implementation checklist

- [x] **Backend:** `backend/portfolio/performance.py` – compute portfolio vs benchmark returns
  - [x] Use `signals.fetcher` for historical close
  - [x] Handle missing tickers (skip or use last known price)
  - [x] Return `{periods: [{period, portfolio_pct, spy_pct, qqq_pct, vs_spy, vs_qqq}], as_of}`
- [x] **API:** Add `performance_vs_benchmark` to dashboard response
  - [x] Call from `get_dashboard()` when portfolio exists
- [x] **Frontend:** `PerformanceVsBenchmark.tsx` component
  - [x] Table: Period | Portfolio | SPY | QQQ | vs SPY | vs QQQ
  - [x] Add to Overview tab (Portfolio Summary section)
- [x] **Config:** Uses SPY, QQQ by default
- [ ] **Verify:** Run dashboard, see Portfolio vs SPY/QQQ for 1m/3m/6m/1y

### Files to create/modify

| File | Action |
|------|--------|
| `backend/portfolio/performance.py` | Create |
| `backend/api/routers/dashboard.py` | Add performance_vs_benchmark |
| `web/components/dashboard/PerformanceVsBenchmark.tsx` | Create |
| `web/components/dashboard/index.ts` | Export |
| `web/components/Dashboard.tsx` | Add component to Overview or Portfolio |

---

## #4: Forward tracking

**Goal:** "What we said vs what happened" – build trust by showing when the model was right or wrong.

### Scope

- **Existing:** `model_validation` compares next-day bias (SPY/QQQ) vs actual. Lives in `signals/validation.py`.
- **Extend:**
  1. **Multi-horizon:** Add 5d, 20d, 60d forward returns for SPY/QQQ (not just 1d).
  2. **Portfolio holdings:** For EOD snapshots, show: "On date D we said X for ticker T. N days later return was Y%."
  3. **Signal accuracy:** When we said CONSIDER TRIM, what was the avg forward return? When HOLD/ADD?

### Implementation checklist

- [x] **Backend:** Extend `signals/validation.py` or add `signals/forward_tracking.py`
  - [x] Add `get_forward_tracking()` with horizons=[5, 20, 60]
  - [x] For each (date D, date D+N): get close at D and at D+N
  - [x] Return records: `{as_of_date, ticker, horizon_days, our_signal, actual_return_pct}`
  - [x] Summary: avg return by horizon (5d, 20d, 60d)
- [x] **Backend:** Add signal-based grouping
  - [x] "When we said CONSIDER TRIM: avg 20d return = X%"
  - [x] "When we said HOLD/ADD: avg 20d return = Y%"
- [x] **API:** Add `forward_tracking` to dashboard
- [x] **Frontend:** Add "Forward tracking" ToggleSection in Analysis tab
  - [x] Table: Date | Ticker | Horizon | Signal | Actual %
  - [x] Summary: avg return by horizon
  - [x] Signal-accuracy table (TRIM vs HOLD vs ADD for 20d)
- [ ] **Verify:** EOD snapshots exist; run dashboard; see forward tracking data

### Files to create/modify

| File | Action |
|------|--------|
| `backend/signals/forward_tracking.py` | Create (or extend validation.py) |
| `backend/api/routers/dashboard.py` | Add forward_tracking |
| `web/components/Dashboard.tsx` | Add/extend Forward tracking UI |
| `web/components/dashboard/ForwardTracking.tsx` | Create (optional) |

### Data requirement

- EOD snapshots in `backend/data/eod/YYYY-MM-DD.json`
- Need ≥2 snapshots for 1d; ≥30+ for meaningful 20d/60d stats
- Run `run_daily.py` regularly to populate EOD

---

## Verification process

1. **#3 Performance vs benchmark**
   - Start backend: `cd backend && uvicorn api.main:app --reload`
   - Start web: `cd web && npm run dev`
   - Open dashboard → Overview or Portfolio tab
   - Check: Table shows Portfolio %, SPY %, QQQ %, vs SPY, vs QQQ for 1m/3m/6m/1y
   - Edge: No portfolio → show message or hide section

2. **#4 Forward tracking**
   - Ensure EOD snapshots exist: `ls backend/data/eod/`
   - If none: run `cd backend && python scripts/run_daily.py` (or wait for daily run)
   - Refresh dashboard → Analysis tab
   - Check: Forward tracking section shows records and summary
   - Edge: &lt;2 EOD snapshots → show "Need more EOD data" message

---

## Resume workflow

When resuming:

1. Open this file (`docs/planning/ROADMAP.md`).
2. Find the next unchecked item in the Implementation checklist.
3. Implement that item.
4. Mark it `[x]` when done.
5. Run verification steps.
6. Commit with message: `feat: #3 performance vs benchmark` or `feat: #4 forward tracking`.

---

*Last updated: initial implementation of #3 and #4*
