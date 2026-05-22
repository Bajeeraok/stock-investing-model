# Product & model backlog

Single living backlog for retail-investor robustness. Implement in small batches; check off when shipped.

## Done (reference)

- [x] **Uncertainty + as-of** — Dashboard `data_freshness`, per-signal `uncertainty` (ST band width %, ATR-based range hint)
- [x] **Portfolio stress / max-pain** — `portfolio_stress` scenarios (parallel −10% / −20% / −30% shock) + UI strip
- [x] **Risk-based sizing in UI** — Explicit risk budget ($), position notional, stop %; Signals table column + banner
- [x] **MT/LT uncertainty** — `uncertainty.mt_*` / `lt_*` band width + narrative in `enrich_signal_uncertainty`; Signals table shows lines
- [x] **Known limits panel** — API `known_limits` (defaults in `dashboard.py`, override via `config.yaml`)
- [x] **Reusable disclaimer** — `ModelDisclaimer` on Overview + Signals
- [x] **Macro vs HMM coaching** — `macro_regime_bundle.coaching_note` when price-HMM and macro disagree
- [x] **Portfolio risk in Doctor** — `portfolio_risk_metrics` (VaR/CVaR, top pair correlations, correlation-adjusted weights) in Portfolio Doctor (`PortfolioRiskMetricsPanel`, 2026-03-30)
- [x] **Earnings caution + quality in UI** — `run_daily` caution window + extra score cut; dashboard `enrich_results_earnings_quality`; Signals table Earnings column (2026-03-30)

## Performance (dashboard load)

- [x] **Shell-first load** — `GET /api/dashboard/shell` serves Redis snapshot instantly; no full compute on navigation
- [x] **Stale-while-revalidate** — 7d `dashboard:last` snapshot + background refresh job + `GET /api/dashboard/status` polling
- [x] **localStorage SWR** — `web/lib/dashboardCache.ts` instant paint on repeat visits
- [x] **Lazy tabs** — signals-panel, opportunities-bundle (best 2026 + opps), analysis-bundle (paper/insider/forward)
- [x] **Deferred main pipeline** — watchlist confidence batch, doctor add recs, analysis parallel tasks off dashboard start
- [x] **Cache TTL 45 min** — default `DASHBOARD_CACHE_TTL_SECONDS=2700`; warm cron documented in `env.example`
- [x] **Market scheduler** — `MARKET_SCHEDULER_ON=1`: pre-market 4:00–9:15 ET + dashboard warm 8:30 & every 25m 9:30–15:45 (`api/market_scheduler.py`)
- [x] **After-hours earnings** — 4:30 PM & 6 PM ET on earnings days only; `after_hours_earnings` on Overview (`signals/after_hours_earnings.py`)

## Trust & clarity

- [ ] Per-field **as-of** when APIs expose it (FMP filing date, last earnings)

## Regime & horizon

- [ ] **Stress labels** on setups (“works better when VIX &lt; X”) — optional refinement beyond coaching banner
- [ ] **Position intent** tags: trade vs invest per ticker or signal

## Risk & portfolio (Bloomberg-style enhancements)

- [ ] **Factor/sector caps** beyond raw concentration (e.g. max tech %)
- [ ] **Liquidity score** — ADV-based days-to-exit at 20% of daily volume, 1–5 scale, flag >5 days; fill existing SignalsTable placeholder column; add summary to PortfolioSummary
- [x] **Portfolio beta** — extract `_compute_beta()` to shared util, compute per-holding + sector + portfolio-weighted beta; display in PortfolioRiskMetricsPanel ("Your portfolio moves 1.4x the market") — 2026-05-19
- [ ] **Enhanced VaR** — add 99% confidence level, dollar amounts, and component VaR decomposition (per-holding contribution to total VaR); extend existing `compute_var_cvar()` + PortfolioRiskMetricsPanel
- [ ] **MCTR (Marginal Contribution to Risk)** — per-holding risk contribution from covariance decomposition; "NVDA contributes 34% of portfolio risk despite being 17% of value"; new MCTRPanel with sorted risk bars in Tier1RiskFeatures
- [ ] **Named historical stress scenarios** — beta-adjusted per-holding impacts for 2008 crash, COVID Mar 2020, 2022 rate hike, dot-com bust; sector ETF proxy when ticker didn't exist; per-holding survivors; new NamedScenarioPanel

## Behavioral

- [x] **Cooldown** after trim/stop (block re-add N days unless thesis update) — 2026-05-19
- [x] **One-line journal** prompt on “Add” from dashboard — 2026-05-19

## Evaluation

- [x] Scheduled **ablation** report (macro gate vs baseline) — `backend/scripts/run_ablation_report.py` writes `data/reports/ablation_<UTC>.json` and `ablation_latest.json` (2026-04-09)
- [x] **Paper vs forward baseline** drift — `signals/paper_vs_backtest_drift.py` + dashboard `paper_vs_backtest_drift` + Analysis tab UI (2026-04-09)

## Engineering

- [ ] Feature flags for FRED/FMP/Yahoo partial failure (degraded mode)
- [x] Structured logging when confidence **omits layers** — `confidence_layer_omitted` in `confidence_engine` (2026-04-09)

## Stage 1 — Signal accuracy

- [ ] **Catalyst detection layer** — classify FMP news headlines by event type (M&A, FDA, earnings surprise, major partnership); flag "catalyst active" when high-impact event in last 48h; add badge to signal card; override message when catalyst + bull regime: "Momentum regime detected — valuation model secondary until catalyst digested". Existing: FMP news feed + keyword lexicon + Layer 7 in confidence engine; gap: no event-type classification or catalyst flag
- [ ] **Post-earnings signal transition** — fire within 24h of report; detect beat/miss from FMP calendar + next-day price action; generate transition signal ("NVDA beat by X% — signal updating"). Existing: pre-earnings caution, HMM gets earnings_context within 5 days, earnings_target_block; gap: no prescriptive post-earnings verdict update
- [ ] **Signal confidence calibration audit** — run backtest_simple.py calibration_score() and build formal reliability diagram (predicted confidence bucket vs actual win rate); surface in Analysis tab. Existing: Platt scaling, calibration_score() monotonicity check, forward_tracking hit rates; gap: no user-facing calibration curve
- [ ] **Momentum regime override** — when bull regime + new 52w high + catalyst present, add momentum continuation target alongside fair value target; elevate existing _momentum_valuation_tension_payload from display-only note to actual signal modifier with separate momentum price target. Existing: tension payload fires as note when 88% bull + 18% above FV; gap: doesn't modify signal or add target
- [x] **Fair value model segmentation** — already segmented: DEEP_VALUE (PE-relative), VALUE (PE-relative), GROWTH (PEG blend), HIGH_GROWTH (forward PE + FCF), Index ETF (risk-premium model), commodities (macro-only). Quality premium + analyst consensus guardrails in place
- [ ] **Pattern score rebalancing** — pattern_score is a near-bottom reversal composite (52w low, RSI oversold, volume climax, MACD reversing, Bollinger); 27-43 range is correct for non-bottom stocks. Review: is 55-60 gate too high? Should score include non-reversal bullish patterns (breakout, cup-and-handle)? Add configurable gate threshold

## Stage 2 — Signal completeness

- [x] **Signal change log** — `behavior/what_changed.py` tracks suggestion changes, MA crosses, RSI extremes, score moves >=10pts, regime flips, MACD flips per ticker between daily runs; surfaces in dashboard "What Changed" section
- [x] **Watchlist alerts (email + Telegram)** — full `alerts/` subsystem with OptionsAlertsEngine, AlertEventStore (JSONL), email (SMTP) + Telegram Bot digests for story changes, trim candidates, earnings-week names, IV extremes
- [x] **Browser push notifications** — Service worker `web/public/sw.js`; FastAPI `api/routers/push.py` (subscribe/unsubscribe/store, optional POST /test + `broadcast_web_push()` for future hooks); Analysis tab **Browser push** panel; env `VAPID_*`, optional `WEB_PUSH_ADMIN_SECRET`. Wire alerts worker → `broadcast_web_push` as a follow-up.
- [x] **Track record dashboard** — Analysis tab **Track record**: key metrics, forward signal table, paper breakdown, calibration diagram; **paper cumulative equity curve** from `paper_trading.equity_curve` (completed trades, compounded index). Further polish (stop-hit rate slice) optional.

## NLP / news sentiment

- [ ] **FinBERT (ProsusAI/finbert)** for layer-7 news sentiment — optional upgrade over keyword lexicon + Alpha Vantage; run batched or async (heavy on CPU if not cached); map FinBERT probs to same −1..1 → 0..1 path as today; add `transformers` / `torch` only if this ships

## Compliance / copy

- [x] **False precision** copy pass — `data_freshness.precision_note`, `ModelDisclaimer` bands line, dashboard price/EOD as-of fields (2026-04-09)

---

## Retail UX — platform comparison & phased roadmap

North star: *Open any ticker and within 5 seconds know Go or wait, where price needs to be, and what could go wrong — without reading a table.*

### Platform feature map

| Platform | Retail strength | Thrive Alpha equivalent | Gap |
|----------|-----------------|-------------------------|-----|
| **TipRanks** | Smart Score 1–10, forward price chart (high/low/avg bands) | Gates + `HorizonProjectionChart` + composite score | Single headline score ring; street vs model bar on One Answer |
| **Robinhood** | One action, minimal chrome, green/red clarity | `retail_action` / Now · Action | Three vocabularies (Plan 7L, Tech+ML, Now) on same row |
| **TradingView** | Screener → chart → alert; preset screens | Signals tab + modal | Wide table; no saved retail views |
| **Finviz** | Sector heat map, color = performance | Regime pie + macro strip | Holdings heat tile grid |
| **Unusual Whales** | Alerts-first home, ticker-filtered feed | Story alerts strip | No “today’s 3 moves” digest |
| **Webull** | Deep analytics | Deep dive tab | Anti-pattern on main surface — keep buried |

### P0 — clarity & consolidation (in progress)

- [x] **Horizon projection chart** — ST/MT/LT bands on ticker One Answer (`HorizonProjectionChart`, `price_history` in API) — 2026-05-19
- [x] **Unify action language** — `Now · Action` / `retail_status` canonical; Plan + Tech+ML → “Model detail” toggle on Signals — 2026-05-19
- [x] **One Answer reorder** — Verdict + headline above chart; detail block below horizon cards — 2026-05-19
- [x] **Slim Signals table** — LIS hidden; retail columns default (Ticker · Close · Now · Gates · Earnings); model detail toggle — 2026-05-19
- [x] **Today's 3 moves** — Overview digest (`TodaysMovesPanel`: story + trim + earnings) — 2026-05-19
- [x] **Chart polish** — Calendar x-axis labels; MA20/50 on history; stronger Now marker — 2026-05-19
- [x] **Fix mojibake copy** — Partial pass on `InvestorDecisionSummary.tsx` (remaining edge cases in long tail strings)

### P1 — differentiation (next)

- [x] **Portfolio heat map** — Holdings as colored tiles (score/regime), click → modal — 2026-05-19
- [x] **Preset signal views** — Pullback buys / Trim candidates / Earnings week on Signals tab — 2026-05-19
- [x] **Street vs model bar** — FMP/Yahoo consensus vs model FV on One Answer — 2026-05-19
- [x] **Position intent tags** — Trade vs invest chip (localStorage); gate hint copy — 2026-05-19
- [x] **Advanced mode toggle** — Hide Analysis + Test Suite until enabled (header toggle) — 2026-05-19
- [x] **Liquidity column** — ADV days-to-exit on signal rows (`enrich_results_liquidity`) — 2026-05-19

### P2 — stickiness & trust

- [x] **Cooldown + journal** on trim/add (see Behavioral section) — 2026-05-19
- [x] **Calibration curve** on Analysis tab — 2026-05-19
- [x] **Catalyst badge** on signals list — 2026-05-19
- [x] **Push digest** wired to gates / regime flips — 2026-05-19

### Do not copy

- Robinhood confetti / gamification (conflicts with decision-support guardrails)
- Webull indicator wall on main screen
- Unusual Whales options flow as default (equity-first product)
- Auto-trade or one-tap buy

---

## Market catalyst board & model track record (2026-05)

North star: *Before the open — what could move the whole market, and does pre-market agree with our regime?*

Implement in order: **P0 → P1 → P2 → P3**. Do not start P2 until P0/P1 ship.

### Ops / Railway (recommendations — apply on production)

| Item | Recommendation | Status |
|------|----------------|--------|
| **`DATA_ROOT`** | Remove `DATA_ROOT=/data` unless a **Railway Volume is mounted at `/data`**. No volume → omit env (defaults to `/app/data`). | User action on Railway |
| **`REDIS_URL`** | Keep connected — EOD snapshots persist across deploys even without a volume. | ✓ on thrive-alpha |
| **`EOD_SCHEDULER_CRON`** | Use in-process APScheduler on API: `0 20 * * 1-5`, `EOD_SCHEDULER_TZ=America/New_York`. **Not** `config.yaml` `eod_schedule_time` alone (that only applies to standalone `scheduler_eod.py`). | Verify in Railway vars |
| **`scheduler_eod.py`** | Separate always-on process; only if not using `EOD_SCHEDULER_CRON`. | Optional |
| **Paper trades file** | `paper_trades.csv` under `DATA_ROOT` — lost on redeploy without volume; forward tracking still OK via Redis EOD. | Known limit |
| **EOD panel path** | Analysis → EOD snapshots shows resolved `{DATA_ROOT}/eod/` | [x] 2026-05-21 |
| **`MARKET_SCHEDULER_ON=1`** | Pre-market 4:00–9:15 ET + dashboard warm; does **not** replace 8pm EOD cron. | Optional |

### Model track record visibility (parallel backlog)

- [ ] **Always show Analysis sections** — Paper trading + forward tracking with empty-state (not hidden until bundle loads).
- [ ] **Preload analysis bundle on Overview** — Model health strip shows ADD 20d hit rate without visiting Markets first.
- [ ] **Advanced mode** — Analysis tab hidden until toggle; document in onboarding copy.

### P0 — Pre-market catalyst board ✅

Glue calendar + pre-market engine + regime tension + FOMC historical stats.

- [x] **`build_market_catalysts()`** — `signals/market_catalysts.py` — 2026-05-21
- [x] **`GET /api/pre-market`** — `market_catalysts` on every response via `_premarket_with_catalysts()` — 2026-05-21
- [x] **`MarketCatalystBoardPanel`** — Under pre-market gauge in `PreMarketPanel` (Markets tab) — 2026-05-21
- [x] **Tests** — `backend/tests/test_market_catalysts.py` — 2026-05-21
- [x] **Morning newsletter** — “Market catalysts” section when pre-market file includes board — 2026-05-21

**P0 payload:** `scheduled_today`, `live_tape`, `tensions`, `flip_narratives`, `summary_line`, FOMC `scenario` stats where available.

### P1 — Event-day flip stats (next)

Historical behavior in similar setups — **not** release forecasts.

- [ ] **`data/market_flip_stats.json`** — Monthly refresh script; gap fade, event-day tables
- [ ] **Gap fade rate** — ES pre-market gap sign vs SPY same-day close sign (backtest)
- [ ] **CPI / NFP date tables** — Extend `event_scenarios.py` beyond FOMC-only (`get_event_reaction_stats`)
- [ ] **Pre-market vs close contradiction** — Join `pre_market_latest.json` history to EOD pairs
- [ ] **UI** — Show on catalyst board: “Gap faded X% on past CPI days (n=…)”

### P2 — Trading-hours extensions (after P1)

- [ ] **Release markers** — 8:30 / 2:00 ET on board (“released” / “pending”)
- [ ] **Since open / since CPI** — SPY move from open and from release timestamp
- [ ] **Intraday refresh** — Optional 1–5 min polling; needs Premium Polygon/FMP or similar
- [ ] **Push digest hook** — “CPI in 30m; pre-market bull; gap-fade history 61%”

### P3 — Unified market state (optional)

- [ ] **`MarketStatePanel` on Overview** — Drivers + catalysts + pre-market + next-day outlook in one card
- [ ] **`GET /api/market-state`** — Optional dedicated endpoint

### Signals / roadmaps ↔ portfolio sync

- [x] **`get_signal_universe()`** — `config_loader`: watchlist + portfolio-only holdings — 2026-05-22
- [x] **`run_signals`** uses signal universe (dashboard + daily EOD) — 2026-05-22
- [x] **API `signal_universe`** — Top-level dashboard field for Roadmaps tab — 2026-05-22
- [x] **Roadmaps tab** — Portfolio holdings first, then watchlist; cap 24 cards with truncation note — 2026-05-22

---

_Add new items at the bottom; move to **Done** with date when shipped._
