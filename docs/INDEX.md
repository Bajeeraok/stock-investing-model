# Docs index (agents)

**Token rule:** Use this file to pick **one** doc to read. Do not load all of `docs/` unless the user asks for a full audit.

**How to use in chat:** `@docs/INDEX.md` then `@docs/<path>` for the matched row.

**Human-friendly tables:** [`README.md`](README.md)

---

## Route by question

| You are asking about… | Read first |
|------------------------|------------|
| Forward tracking, frozen gates, TRIM score, audit cohort | [`audit/SIGNAL_AUDIT_FORWARD_TRACKING.md`](audit/SIGNAL_AUDIT_FORWARD_TRACKING.md) |
| Trim / exit gates (score + 2/4 confirmers) | [`signals/TRIM_GATE_DESIGN.md`](signals/TRIM_GATE_DESIGN.md) |
| ST/MT/LT bands, entry zones, gates, retail verdict | [`signals/PRICE_BANDS_AND_GATES_REFERENCE.md`](signals/PRICE_BANDS_AND_GATES_REFERENCE.md) |
| Valuation deck, street vs model FV, analyst bar | Code: `valuation_deck.py`, `AnalystRatingBar.tsx` — no dedicated doc yet |
| Entry band touch % / timing | `backend/signals/entry_band_touch.py`, `build_entry_band_touch_rates.py` |
| FMP keys, endpoints, field mapping | [`data/FMP_DATA_MAPPING.md`](data/FMP_DATA_MAPPING.md), [`data/DATA_SOURCES.md`](data/DATA_SOURCES.md) |
| API/dashboard JSON shapes | [`data/DATA_CONTRACT.md`](data/DATA_CONTRACT.md) |
| Backtest scripts, hit rates, walk-forward limits | [`signals/BACKTEST_SIGNALS.md`](signals/BACKTEST_SIGNALS.md), [`backend/BACKTEST_DATA.md`](backend/BACKTEST_DATA.md) |
| Direction/range accuracy, EOD validation | [`signals/VALIDATING_MODEL_PREDICTIONS.md`](signals/VALIDATING_MODEL_PREDICTIONS.md), [`signals/MODEL_VALIDATION.md`](signals/MODEL_VALIDATION.md) |
| Rotation, breadth, RS step-down | [`signals/ROTATION_AND_PROBABILITY_ANALYSIS.md`](signals/ROTATION_AND_PROBABILITY_ANALYSIS.md) |
| Retail one-liner / decision UX | [`signals/RETAIL_ONE_ANSWER_DESIGN.md`](signals/RETAIL_ONE_ANSWER_DESIGN.md), [`signals/ALERTS_RETAIL_QUICK_DECISION.md`](signals/ALERTS_RETAIL_QUICK_DECISION.md) |
| Dashboard UI, local dev | [`web/DASHBOARD_README.md`](web/DASHBOARD_README.md) |
| Deploy / Railway | [`operations/deploy-railway.md`](operations/deploy-railway.md) |
| Product direction, roadmap (not code) | [`planning/PRODUCT_THESIS.md`](planning/PRODUCT_THESIS.md), [`planning/ROADMAP.md`](planning/ROADMAP.md) |

**Runtime architecture** is in repo root [`CLAUDE.md`](../CLAUDE.md) — prefer that over planning docs for implementation tasks.

---

## All docs (one line each)

### `signals/` → `backend/signals/`

| File | Summary |
|------|---------|
| `PRICE_BANDS_AND_GATES_REFERENCE.md` | ST/MT/LT bands, ATR stops, four primary gates, horizon entry calculator |
| `RETAIL_ONE_ANSWER_DESIGN.md` | Single retail verdict on ticker detail / investor summary |
| `ALERTS_RETAIL_QUICK_DECISION.md` | Alert thresholds and quick-decision copy |
| `BACKTEST_SIGNALS.md` | `backtest_*.py`, BUY/HOLD/SELL buckets, target hit scripts |
| `BACKTEST_CONFIDENCE.md` | A/B/C backtest tiers, exit validation, primary KPIs |
| `TRIM_GATE_DESIGN.md` | Trim gate stack (2/4 v1), EOD freeze, forward tracking cohorts |
| `MODEL_VALIDATION.md` | `validation.py`, typical move, next-day bias panel |
| `VALIDATING_MODEL_PREDICTIONS.md` | EOD-pair direction/range accuracy methodology |
| `INDICATOR_COMPARISON_MATRIX.md` | RSI/MA/MACD vs external sources |
| `ROTATION_AND_PROBABILITY_ANALYSIS.md` | `breadth_rs.py`, tech vs equal-weight rotation |
| `RETAIL_QUANT_REVIEW.md` | Cross-cutting quant + retail UX review |

### `data/` → providers + `config.yaml` `data.*`

| File | Summary |
|------|---------|
| `DATA_SOURCES.md` | FMP, FRED, Polygon, Finnhub, yfinance roles and fallbacks |
| `FMP_DATA_MAPPING.md` | `fmp_client.py` endpoint → dashboard fields |
| `DATA_CONTRACT.md` | Stable API payload shapes for web |

### `audit/` → forward track record

| File | Summary |
|------|---------|
| `SIGNAL_AUDIT_FORWARD_TRACKING.md` | **Canonical** audit store design, EOD freeze, path metrics, UI cohort |

> **Duplicate:** `docs/SIGNAL_AUDIT_FORWARD_TRACKING.md` at repo `docs/` root is legacy — use `audit/` copy only.

### `backend/` → API & scripts

| File | Summary |
|------|---------|
| `BACKTEST_DATA.md` | Backtest caches, earnings exclusion, data limits |

### `web/` → Next.js app

| File | Summary |
|------|---------|
| `DASHBOARD_README.md` | Tabs, proxy to FastAPI, component map |

### `operations/`

| File | Summary |
|------|---------|
| `deploy-railway.md` | Production deploy on Railway |

### `planning/` (product; skip for narrow code fixes)

| File | Summary |
|------|---------|
| `PRODUCT_THESIS.md` | One-page positioning |
| `ANALYSIS_AND_RECOMMENDATIONS.md` | Product analysis |
| `IMPLEMENTATION_ROADMAP.md` | Phased delivery checklist |
| `IMPROVEMENT_PLAN.md` | Improvement themes |
| `FUTURE_FEATURES.md` | Ideas backlog |
| `ROADMAP.md` | High-level roadmap |

### Root (repo)

| File | Summary |
|------|---------|
| [`../CLAUDE.md`](../CLAUDE.md) | Always-on agent context: architecture, modules, endpoints |
| [`../README.md`](../README.md) | Quick start |
| [`../TODO.md`](../TODO.md) | Active backlog |
