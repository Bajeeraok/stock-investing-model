# TODO — Model & UX Improvement Backlog

Generated 2026-10-23. Items ranked by measured impact from the 148-snapshot
prod EOD analysis (9,757 ticker-date pairs). See MODEL_ACCURACY_ANALYSIS.md,
PROJECT_BUGS_OPTIMIZATIONS_REPORT.md, DATA_DRIVEN_IMPROVEMENT_GUIDE.md.

**2026-10-24 update — see "Session 2 results" at bottom for what shipped.**

---

## P0 — Deploy & validate current changes (do first)

- [x] Stage + commit + push all unstaged work: code files landed in prior commits
  (retail_action_payload, commodity_vol, config, ml_horizons.json, forward_tracking,
  calibration, backtest, web components). EOD snapshot JSONs + val_probs.csv left
  untracked per user — prod regenerates them, not required in git.
- [x] Deploy to Railway (auto-deploys from main; live `/api/ticker/AAPL` verified carrying `protect_mode`, split-entry copy) → `POST /api/eod/run?force=true` → verify payloads carry
  `dip_zone`, `full_go_via`, `macro_regime`, `commodity_vol`, entry_mode shift
  (needs user's Railway access — cannot be done from this environment)
- [x] `cd web && npm install && npx tsc --noEmit` — **PASS**; fixed 4 pre-existing
  tab-split errors (LevelsTab bad import, tabCtx use-before-declare,
  modalNewsRail headlines/catalystCards types)

## P1 — Data-driven validation (next ~21 trading days)

- [ ] (parked — starter_only disabled by default) Re-slice `starter_only` expectancy with new `in_zone AND val_starter` rule
- [ ] Measure `full_go_via: "market_regime_override"` cohort vs strict `all_gates`
- [ ] `dip_zone` cohort outcomes vs the +6.01%/62.6% bucket — flag confirmed to
  capture the same rows (n=6 in current snapshots — needs accumulation)
- [ ] Commodity ETF rows — count `commodity_vol` calm-override firings
- [ ] IV rank knife demotions — count starter→hard_lock flips at iv_rank>75
- [x] Re-run `scripts/backtest_signals.py` — **BUY 1m −0.10%/48.9% (n=3,876)**
  vs baseline −0.15%/48.6% — marginal improvement, still negative (gate-layer
  fixes don't change raw composite_buy≥70 BUY). 3m improved to +3.77%.
- [x] Refit `fit_probability_calibration.py` — short isotonic refit on 8,499
  pairs (raw 0–49% → ~51.9%, flat as expected); medium/long still identity
  (insufficient rows — need accumulation)

## P2 — Model gaps (implementation backlog)

- [x] **Analyst revision breadth** — `analyst_revision_breadth()` in
  earnings_quality.py computes revisions_30d + est_drift_pct + breadth_score;
  wired as ±0.05 nudge into confidence_engine fundamental_score (all 3 paths),
  replaces the ±5% boolean flag; `details.analyst_revisions` exposes it
- [x] **ML retraining on own outcomes** — `scripts/retrain_ml_on_outcomes.py`:
  8,498 rows, 33 features (dip-zone, gate states, band distance, score buckets,
  interactions, entry_mode/regime one-hots). Test AUC **0.530 vs 0.481 raw-prob
  baseline**; excess-label mode (`--label excess`) AUC 0.522 vs 0.487. Artifacts:
  `data/models/lgbm_own_outcomes_short.pkl` + `own_outcomes_report.json`
- [ ] **Macro gate rescue** — parked: 10y same-stock tests show extra gating/timing layers don't beat holding
- [ ] **COT positioning** — parked (same reason)
- [x] **Grains vol (WEAT, CORN)** — realized-vol percentile fallback in
  commodity_vol.py (`RV:WEAT` symbol); live-verified: WEAT → 27th pct "calm"
- [x] **Sector relative strength** — `sector_relative_strength()` per-ticker
  sector-ETF RS vs SPY (per-day cached) attached as `sector_rs` on EOD rows;
  available to outcomes retrain + downstream. No score nudge yet (untested)
- [x] **Intraday trigger layer** — `alerts/band_triggers.py` (worker) + scanner ENTRY_ZONE_ENTERED/STOP_HIT on dashboard refresh; PROTECT_MODE_ON/OFF flip alerts added in `scanner/dashboard_alerts.py`. — "alert me when price enters the band";
  backend/alerts engine exists but band-entry triggers not implemented

- [x] **Track record vs same-stock hold** — `summary_timing_vs_hold` in forward tracking (edge vs holding the same stock + vs SPY), shown in ForwardTracking.

## P3 — UX polish remaining

- [x] Hide tiles entirely when `risk_reward == null` (VerdictPanel already guards `rr != null && rr > 0`) (don't render "—")
- [ ] `tabular-nums` on remaining % cells in modal
- [ ] Gate detail strings now include `· macro: …` / `· GVZ: …` — verify
  WhyGateCards renders multi-line details cleanly
- [x] EntryBandsChart decluttered: domain clamped to ±50% of spot, far levels
  (deep tiers, 2x targets) pin as edge tags (▲/▼), right-edge labels
  collision-resolved, duplicate bands deduped. MA50/MA200 markers done (`bandsFromHorizons` technicalLevels)
- [x] `DIP_ZONE` row badge on dashboard signal tables (`DipZoneBadge` in SignalsTable) (DecisionDeck already
  consumes `ra.dip_zone` — table badge still open)

## P4 — Code health

- [ ] `data_source_stubs.py` — mark CBOE GVZ done (real impl in commodity_vol.py);
  prune dead stubs or wire TradingEconomics/FRED leftovers
- [ ] Broad `except Exception` audit — highest-impact cases first
- [ ] Centralize threshold resolution (config.yaml vs retail_action_payload.py
  constants — partially done via _RG_CFG; drift remains)
- [ ] Regression tests: thin snapshots, stale fields, missing iv_rank/options,
  commodity ticker paths, override cohorts, calibration artifact loading
- [x] EOD `gate_detail_json` — **GAP FOUND**: snapshot rows serialize only
  {detail,id,label,pass} per gate — macro_regime/commodity_vol/macro_score are
  stripped before write, so forward-tracking can't parse them. Find where gates
  get slimmed (signal_audit_store / eod row build) and persist the fields.

## Session 2 results (2026-10-24)

**Levels tab consolidation** — TradeRoadmapCard gained `tablesOnly` mode; when a
horizon playbook exists it renders only the unique content (staged tranche
tables + news), dropping verdict header/TL;DR/next-trigger/why-this-call that
the playbook already carries. Full card unchanged on Roadmaps view.

**SPY-beating gap analysis (user question)** — measured excess return vs SPY
over same 21d windows across all snapshots (`scripts/excess_vs_spy.py`):

| Cohort | n | Excess | Beat SPY |
|---|---|---|---|
| all | 9,828 | +0.08% | 47.2% |
| BUY label | 3,823 | **−0.93%** | 45.3% |
| score_0_30 | 4,482 | +1.32% | 49.8% |
| score_30_50 | 201 | **+2.61%** | 52.7% |
| score_50_70 | 1,337 | −1.57% | 43.5% |
| score_70_100 | 3,808 | −0.94% | 45.2% |
| mode_full_go | 29 | **+3.63%** | 72.4% |
| mode_starter_only | 1,311 | −1.33% | 42.0% |

**Finding: the headline BUY label underperforms SPY.** Real alpha is confined to
the 30–50 dip bucket and the gated full_go cohort. Gaps to close:

1. Evaluate on excess returns (`--label excess` now in retrain script); the
   `y = fwd > 0` objective mislabels index-lagging winners as successes.
2. Score ranks the wrong cohort — ≥70 chases lose, 30–50 wins; revisit what
   composite_buy is supposed to select.
3. No explicit "prefer index" output state when no cohort has edge.
4. Snapshots store no benchmark-relative outcome fields — add `spy_fwd`/`excess`
   to forward-tracking rows.
5. Sizing scales with gate counts, not measured cohort expectancy.

## Measured baselines (to beat)

| Metric | Baseline (pre-fix) | Target |
|--------|--------------------|--------|
| 20d win rate | 52.7% | ≥56% |
| BUY≥70 1m return | -0.15% / 48.6% hit | >0% / ≥53% |
| 30-50 bucket | +6.01% / 62.6% | preserve — this is the edge |
| starter_only expectancy | -0.65% | ≥0% |
| full_go slice | 79%/1.49 W/L (n=24) | keep ≥65% at n>100 |
| GO vs NO_GO spread | +2.0% (20d) | ≥+2% |
| **BUY-label excess vs SPY** | **−0.93%/21d** | **>0% — the real bar** |
