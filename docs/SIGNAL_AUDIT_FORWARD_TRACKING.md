# Signal Audit & Forward Tracking — Design Document

**Goal:** Give Thrive Alpha a credible, queryable audit of model outputs across **100 tickers × 30 calendar days**, with outcomes filled automatically — the foundation for subscription-grade track record claims.

**Status:** Design (May 2026)  
**Audience:** Engineering + product  
**Related:** `paper_trade_logger.py`, `forward_tracking.py`, `TrackRecordPanel.tsx`, `MODEL_VALIDATION.md`

---

## 1. Executive summary

The repo already has the **bones** of forward tracking:

| Component | What it does today | Limitation |
|-----------|-------------------|------------|
| `PaperTradeLogger` | Appends `paper_trades.csv`; fills 20d outcomes from EOD | Triggered mainly on **dashboard refresh**, not `run_daily.py`; missing gates, MT target, sector, retail verdict |
| `forward_tracking.py` | Recomputes returns from EOD pairs | **Reconstructs** signal from trimmed EOD rows; no frozen gate/confidence snapshot |
| EOD snapshots | `data/eod/YYYY-MM-DD.json` | Stores **trimmed** `run_results` — not full `retail_action` / investor narrative |
| `TrackRecordPanel` | UI for calibration + paper summary | Cohort = watchlist/portfolio union; gates not broken out |

**Recommendation:** Add a dedicated **Signal Audit Store** (SQLite first) with immutable **signal capture** at run time and a daily **outcome resolver**. Keep CSV export for spreadsheet workflows. **Postgres is not required for the 30-day pilot**; plan a migration path if Thrive Alpha becomes multi-tenant hosted SaaS.

---

## 2. Success criteria (30-day pilot)

After 30 calendar days of daily EOD runs on a fixed 100-ticker cohort, the product should answer:

### Quantitative (must-have)

- Win rate / avg return by **retail signal** (BUY, WATCH, HOLD, TRIM/REDUCE)
- Win rate by **gate count** (0–4 primary gates pass)
- Win rate by **market regime** (UP / NEUTRAL / DOWN) and **HMM bull %** bucket
- Win rate by **sector** and **market-cap bucket**
- **False positive rate:** BUY/GO with negative 30d return or stop hit first
- **False negative rate:** NO-GO/WATCH names that hit ST target before stop
- ST target hit vs stop hit (path-aware, using EOD high/low when available)
- Max gain % / max drawdown % in window (7d and 30d)

### Qualitative (must-have)

- Tickers / sectors where model is consistently wrong
- Confidence bands that are well-calibrated vs not (reliability diagram by cohort)
- Regime detection accuracy (did STRONG_BULL / COLD resolve as expected?)

### Credibility bar (marketing-ready statement)

Example target copy (only after data supports it):

> “BUY signals with all 4 gates passing on S&P 500 names: 67% win rate, +8.4% avg winner, −3.2% avg loser, 2.6× risk/reward — measured across 100 tickers, Jan–May 2026, next-session fills with costs.”

---

## 3. Current architecture (as-is)

```
run_daily.py / dashboard refresh
        │
        ▼
   run_signals()  ──► full row (ML, bands, retail_status, …)
        │
        ├──► save_last_run.json / EOD snapshot (_eod_payload TRIMmed)
        │
        └──► PaperTradeLogger.log_signals_from_results()  [dashboard only today]
                    │
                    └──► paper_trades.csv (+ MTM jsonl)
                              │
                              └──► fill_outcomes() from EOD chain

forward_tracking.py ──► re-reads EOD, pairs D → D+N, score/ML signal bucket
```

### What EOD already stores (per ticker)

`composite_buy`, `signal`, `regime`, `rsi`, `close`, `st_band`, `mt_band`, `short/medium/long_suggestion`, MAs, MACD, etc.

### What EOD does **not** store (but UI shows)

- `retail_action.gates` (valuation / regime / momentum / ML)
- `go_no_go`, `gates_passed`, `gates_locked_count`
- `model_confidence_pct` band (fused 7-layer)
- `overall_verdict` (WATCH vs BUY retail framing)
- `stock_regime_bull_pct` vs `market_regime_bull_pct`
- `temperature` / playbook status (if used in copy)
- Config hash / model version (reproducibility)

**Implication:** Forward tracking from EOD alone cannot reproduce the **same audit the user saw in the ticker modal**.

---

## 4. Gaps vs your spreadsheet spec

| Your column | Today | Gap |
|-------------|-------|-----|
| Date/time | `date` in CSV | No run timestamp; session date only |
| Ticker | ✓ | — |
| Signal (BUY/WATCH/…) | Partial | CSV uses ML `signal`; retail `overall_verdict` / `go_no_go` not logged |
| Confidence range | `ml_confidence` only | No fused confidence low/high |
| Price at signal | `entry_price` | ✓ (if dashboard ran) |
| Stop / ST / MT target | ST band only | MT target missing; stop = band low not labeled swing/build/thesis |
| Regime | `regime` | Often global market regime; stock HMM % missing |
| Temperature | — | Not captured |
| Gate result GO/NO-GO | — | Not captured |
| Gates passed (x of 4) | — | Not captured |
| RSI | In EOD | Not in paper CSV |
| Sector | — | Not captured |
| Outcome 7d / 30d | 20d horizon only | Need explicit 7d + 30d columns |
| Hit stop / hit target | Partial | Path logic exists but not aligned to retail stops |
| Max gain / max loss | — | Not stored |
| Verdict WIN/LOSS/NEUTRAL | `outcome` | Needs rule table per signal type |

Additional **process** gaps:

1. Logging tied to **dashboard refresh** — missed if only cron EOD runs.
2. Cohort is **watchlist + portfolio**, not a deliberate 100-name audit set.
3. `forward_tracking.json` is read by calibration but **nothing writes it**.
4. `confidence_calibration.py` EOD loader expects `snap["tickers"]` — mismatches real `run_results` shape.

---

## 5. Recommended architecture

### 5.1 Design principles

1. **Capture once, immutably** at signal generation time (what the user would have seen).
2. **Resolve outcomes separately** from EOD/OHLCV (idempotent daily job).
3. **Aggregate for UI** — don’t scan raw rows on every dashboard load.
4. **Same pipeline for live and backtest** — backtest writes to a parallel table with `source=backtest`.

### 5.2 Storage choice: SQLite now, Postgres later

| Option | 100×30 pilot | Pros | Cons |
|--------|--------------|------|------|
| **CSV only** | Works | Simple export | Slow grouped queries; rewrite-on-update fragile |
| **SQLite** ✓ recommended | ~3k signal rows + ~90k path rows | SQL aggregations; single file; fits current stack | Single-writer; backup discipline |
| **Postgres** | Overkill now | Multi-user, concurrent writes, hosted | Ops burden; not used anywhere in repo today |

**Scale check:** 100 tickers × 30 days = **3,000 signal rows**. Even with daily path snapshots, **< 100k rows** — SQLite is comfortable.

**Postgres trigger:** Move when you need (a) cloud-hosted multi-tenant audit, (b) concurrent writers (API + worker + analytics), or (c) retention > ~2 years with heavy ad-hoc SQL.

Default path: `DATA_ROOT/signal_audit.db` (+ nightly export to `signal_audit_export.csv`).

### 5.3 Pipeline (target)

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. CAPTURE (after run_signals, same run as EOD)                  │
│    scripts/run_daily.py  AND  dashboard bundle (idempotent)      │
│    → SignalAuditWriter.log_run(results, run_meta)                │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│ 2. ENRICH (optional same pass)                                   │
│    retail_action via enrich_dashboard_signal_row / lightweight   │
│    gate builder — avoid full ticker_detail for all 100           │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│ 3. OUTCOME RESOLVER (daily cron, after EOD)                      │
│    scripts/resolve_signal_outcomes.py                            │
│    → price_7d, price_30d, hit_stop, hit_st_target, max_gain/loss │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│ 4. AGGREGATE (daily)                                             │
│    scripts/build_audit_report.py → audit_summary.json            │
│    API GET /api/audit/summary, /api/audit/records                │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│ 5. UI — Track Record / new “Model audit” tab                     │
│    Cohort filters, gate breakdown, sector heatmap, export CSV    │
└─────────────────────────────────────────────────────────────────┘
```

**Migrate `paper_trades.csv`:** Backfill into SQLite; keep CSV append for backward compatibility one release, then deprecate.

---

## 6. Data model

### 6.1 Table: `signal_events` (immutable capture)

One row per `(signal_date, ticker, run_id)` — primary audit grain.

```sql
CREATE TABLE signal_events (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id          TEXT NOT NULL,           -- uuid or YYYY-MM-DDTHH:MM ET hash
  signal_date     TEXT NOT NULL,           -- America/New_York session date
  signal_ts       TEXT NOT NULL,           -- ISO8601 capture time
  ticker          TEXT NOT NULL,
  sector          TEXT,
  market_cap_bucket TEXT,                  -- large | mid | etf | problem
  cohort_tag      TEXT NOT NULL DEFAULT 'audit_100',

  -- What we showed the user
  retail_verdict    TEXT,                  -- STRONG BUY | BUY | WATCH | WAIT | REDUCE
  ml_signal         TEXT,                  -- run_signals signal field
  go_no_go          TEXT,                  -- GO | NO-GO | MIXED
  gates_passed      INTEGER,
  gates_total       INTEGER DEFAULT 4,
  gate_detail_json  TEXT,                  -- [{id, pass, visual_status, detail}, ...]

  -- Prices & levels at signal
  price_at_signal   REAL NOT NULL,
  price_source      TEXT,                  -- ohlcv_last_bar | fmp_batch | yahoo
  stop_swing        REAL,
  stop_build        REAL,
  stop_thesis       REAL,
  st_target         REAL,
  mt_target         REAL,
  lt_target         REAL,
  entry_zone_low    REAL,
  entry_zone_high   REAL,

  -- Context
  composite_score   REAL,
  rsi               REAL,
  regime_label      TEXT,                  -- UP | NEUTRAL | DOWN
  hmm_bull_pct      REAL,                  -- stock-specific
  market_hmm_bull_pct REAL,
  ml_short_prob     REAL,
  ml_medium_prob    REAL,
  ml_long_prob      REAL,
  confidence_low    REAL,
  confidence_high   REAL,
  temperature       TEXT,                  -- HOT | WARM | COLD | null

  -- Reproducibility
  config_hash       TEXT,                  -- hash of score + confidence thresholds
  model_version     TEXT,                  -- git sha or package version
  decision_snapshot TEXT,                  -- optional compressed JSON subset

  source            TEXT NOT NULL DEFAULT 'live',  -- live | backtest
  UNIQUE(signal_date, ticker, cohort_tag, source)
);
CREATE INDEX idx_signal_events_date ON signal_events(signal_date);
CREATE INDEX idx_signal_events_ticker ON signal_events(ticker);
CREATE INDEX idx_signal_events_gates ON signal_events(gates_passed, go_no_go);
```

### 6.2 Table: `signal_outcomes` (filled by resolver)

```sql
CREATE TABLE signal_outcomes (
  signal_event_id   INTEGER PRIMARY KEY REFERENCES signal_events(id),
  resolved_ts       TEXT NOT NULL,

  price_7d          REAL,
  price_30d         REAL,
  return_7d_pct     REAL,
  return_30d_pct    REAL,

  hit_stop_swing    INTEGER,               -- 0/1/null (insufficient data)
  hit_st_target     INTEGER,
  hit_mt_target     INTEGER,

  max_gain_pct      REAL,                  -- max favorable excursion in window
  max_drawdown_pct  REAL,                  -- max adverse excursion in window
  path_days         INTEGER DEFAULT 30,

  verdict           TEXT,                  -- WIN | LOSS | NEUTRAL | PENDING
  verdict_rule      TEXT,                  -- e.g. buy_gate4_v1
  benchmark_return_30d_pct REAL,           -- SPY same window
  notes             TEXT
);
```

### 6.3 Table: `signal_path_daily` (optional, for charts)

Daily mark for each open signal — powers drawdown charts without re-scanning EOD.

```sql
CREATE TABLE signal_path_daily (
  signal_event_id INTEGER NOT NULL,
  path_date       TEXT NOT NULL,
  close_price     REAL,
  high_price      REAL,
  low_price       REAL,
  return_pct      REAL,
  PRIMARY KEY (signal_event_id, path_date)
);
```

### 6.4 Table: `audit_daily_summary` (materialized)

Precomputed for dashboard — rebuilt nightly.

```sql
CREATE TABLE audit_daily_summary (
  summary_date    TEXT PRIMARY KEY,
  cohort_tag      TEXT,
  n_signals       INTEGER,
  n_with_outcomes INTEGER,
  payload_json    TEXT NOT NULL             -- full breakdown blob
);
```

### 6.5 Mapping to your spreadsheet columns

| Col | Field(s) |
|-----|----------|
| A Date | `signal_date`, `signal_ts` |
| B Ticker | `ticker` |
| C Signal | `retail_verdict` (+ `ml_signal` for debug) |
| D Confidence | `confidence_low`–`confidence_high` |
| E Price | `price_at_signal` |
| F Stop | `stop_swing` |
| G ST target | `st_target` |
| H MT target | `mt_target` |
| I Regime | `regime_label` + `hmm_bull_pct` |
| J Temperature | `temperature` |
| K Gate result | `go_no_go` |
| L Gates passed | `gates_passed` / `gates_total` |
| M RSI | `rsi` |
| N Sector | `sector` |
| O–U Outcomes | `signal_outcomes.*` |

---

## 7. Verdict rules (explicit, versioned)

Store `verdict_rule` string so marketing numbers are reproducible.

### BUY / STRONG BUY / GO (buy-side)

| Result | Verdict |
|--------|---------|
| Hit ST target before swing stop within 30d | **WIN** |
| Return_30d ≥ +3% and no stop hit | **WIN** (configurable) |
| Hit swing stop before target | **LOSS** |
| Return_30d between −3% and +3% | **NEUTRAL** |
| Return_30d ≤ −3% | **LOSS** |

### WATCH / NO-GO (non-action)

| Result | Verdict |
|--------|---------|
| Avoided loss (return_30d ≤ 0 while NO-GO) | **WIN** (correct caution) |
| Rose > +5% without user entry | **LOSS** (false negative / missed move) |
| Flat | **NEUTRAL** |

### TRIM / REDUCE

| Result | Verdict |
|--------|---------|
| return_30d ≤ 0 | **WIN** |
| return_30d > +5% | **LOSS** |

Implement in `signals/signal_audit_verdict.py` with unit tests.

---

## 8. 100-ticker audit cohort

Add to `config.yaml`:

```yaml
signal_audit:
  enabled: true
  cohort_tag: audit_100
  # Fixed list — do not drift with watchlist edits during pilot
  tickers:
    - AAPL
    - MSFT
    # ... full list per your categories
  categories:
    large_cap_tech: 20
    large_cap_non_tech: 20
    mid_cap_growth: 20
    etfs: 15
    macro_commodity: 10
    problem_names: 15
  retention_days: 365
  outcomes:
    horizons_calendar_days: [7, 30]
    trading_day_mode: true          # map via EOD snapshot chain
    use_intraday_touch: true        # high/low for stop/target
  capture:
    on_run_daily: true
    on_dashboard: true              # idempotent duplicate OK
    include_non_cohort: false       # only audit list during pilot
```

**Run discipline:** One authoritative run per session — **`run_daily.py` at market close** (or scheduler). Dashboard refresh should not be the only writer.

**Deduping:** `UNIQUE(signal_date, ticker, cohort_tag)` — second run same day updates only if `run_id` is newer *and* `decision_snapshot` hash changed (config deploy); otherwise skip.

---

## 9. API & UI

### 9.1 New endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /api/audit/summary?cohort=audit_100&days=30` | Headline stats for Track Record |
| `GET /api/audit/breakdown?by=sector\|gates\|regime\|signal` | Drill-down tables |
| `GET /api/audit/records?...` | Paginated raw audit rows (export) |
| `GET /api/audit/cohort` | Cohort definition + category tags |
| `POST /api/audit/resolve` | Admin: trigger outcome resolver (cron uses script) |

### 9.2 UI (`TrackRecordPanel` evolution)

**Section A — Pilot status banner**

- “Day 12 of 30 · 100 tickers · 1,200 signals captured · 840 outcomes pending”

**Section B — Headline cards (gate-aware)**

- All 4 gates GO: win rate, avg win, avg loss, R/R
- 2–3 gates: same
- WATCH/NO-GO: % avoided drawdown

**Section C — Breakdown tabs**

- By signal · By sector · By regime · By confidence decile

**Section D — Export**

- Download CSV matching spreadsheet columns

**Section E — Methodology footnote**

- Fill mode (`next_session`), costs, verdict rule version, cohort list as-of date

---

## 10. Backtest layer (after live pilot)

Reuse `backtest_signals.py` / `collect_forward_records()` with **`source=backtest`** inserts.

| Period | Dates | Purpose |
|--------|-------|---------|
| Bull | Jan 2023 – Dec 2023 | Regime stress |
| Mixed | Jan 2024 – Jun 2024 | Volatility |
| Current | Jan 2026 – present | Live overlap |

Same schema → same UI filters. Label clearly: **“Historical simulation”** vs **“Live forward audit”**.

---

## 11. Implementation phases

### Phase 0 — Fix existing footguns (2–3 days)

- [ ] Hook `PaperTradeLogger` / new writer into **`run_daily.py`** (not dashboard-only)
- [ ] Fix `confidence_calibration.py` EOD loader (`run_results` not `tickers`)
- [ ] Align forward tracking ticker list with audit cohort when configured
- [ ] Document `DATA_ROOT` persistence for Docker

### Phase 1 — Signal Audit Store (1 week)

- [ ] `signals/signal_audit_store.py` — SQLite schema + migrations
- [ ] `SignalAuditWriter.log_from_run_results()` — map fields from enriched dashboard row
- [ ] Lightweight gate enrichment without full `ticker_detail` for 100 names
- [ ] `config.signal_audit` cohort list (100 tickers)
- [ ] Unit tests: idempotency, field mapping, gate counts

### Phase 2 — Outcome resolver (3–5 days)

- [ ] `scripts/resolve_signal_outcomes.py` — 7d / 30d, path max gain/loss
- [ ] `signal_audit_verdict.py` — rule engine
- [ ] Scheduler hook after EOD snapshot save
- [ ] Backfill script for existing EOD history on cohort

### Phase 3 — Reporting & UI (1 week)

- [ ] `scripts/build_audit_report.py` → `audit_summary.json`
- [ ] API routes + `TrackRecordPanel` / new **Model Audit** section
- [ ] CSV export endpoint

### Phase 4 — Historical backtest parity (1 week)

- [ ] Batch backtest writer to `signal_events` with `source=backtest`
- [ ] Three-period report template for marketing page

---

## 12. Relationship to existing modules

| Module | Action |
|--------|--------|
| `paper_trade_logger.py` | **Extend** or wrap — migrate to SQLite; keep CSV export |
| `forward_tracking.py` | **Keep** for SPY/QQQ quick dashboard; audit store becomes source of truth for cohort |
| `paper_vs_backtest_drift.py` | Point at audit summaries |
| `confidence_calibration.py` | Read from `signal_events` + outcomes |
| `monthly_signal_report.py` | Generate from audit DB |
| EOD snapshots | Add optional `audit_fields` subset to `run_results` for replay without DB |

---

## 13. Ops & integrity

- **Config hash:** Hash `score.buy_min`, `score.sell_max`, confidence thresholds on each run.
- **Run ID:** `{signal_date}:{config_hash[:8]}:{run_source}`.
- **No retroactive edits** to `signal_events` — fixes go in new runs with note.
- **Backup:** Copy `signal_audit.db` with EOD directory nightly.
- **Monitoring:** Alert if `run_daily` misses a session or capture count < 95 for cohort.

---

## 14. Open decisions

| Question | Recommendation |
|----------|----------------|
| SQLite vs Postgres for pilot? | **SQLite** |
| Retail verdict vs ML signal as primary? | **Retail verdict** for UI; store both |
| Log all 100 daily or only “actionable”? | **All 100 daily** — WATCH/NO-GO false-negative analysis requires it |
| Full `investor_summary` snapshot? | Store **compact `decision_snapshot` JSON** (~2–4 KB), not full ticker_detail |
| Temperature field | Derive from playbook / regime module or omit until defined in backend |

---

## 15. Appendix — suggested 100-ticker list

Use the deliberate cohort from the product brief (large cap tech 20, non-tech 20, mid cap 20, ETFs 15, macro 10, problem 15). Maintain in `config/signal_audit_cohort.yaml` so watchlist edits don’t break the pilot.

Problem-name bucket purpose: measure **known failure modes** (spinoffs, low volume, biotech binary) — expect weaker metrics; exclude from headline marketing stats unless labeled separately.

---

*This document supersedes ad-hoc CSV-only `signal_logger.py` sketches — implement as an extension of existing `PaperTradeLogger` + EOD infrastructure rather than a parallel system.*
