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

## Trust & clarity

- [ ] Per-field **as-of** when APIs expose it (FMP filing date, last earnings)

## Regime & horizon

- [ ] **Stress labels** on setups (“works better when VIX &lt; X”) — optional refinement beyond coaching banner
- [ ] **Position intent** tags: trade vs invest per ticker or signal

## Risk & portfolio (Bloomberg-style enhancements)

- [ ] **Factor/sector caps** beyond raw concentration (e.g. max tech %)
- [ ] **Liquidity score** — ADV-based days-to-exit at 20% of daily volume, 1–5 scale, flag >5 days; fill existing SignalsTable placeholder column; add summary to PortfolioSummary
- [ ] **Portfolio beta** — extract `_compute_beta()` to shared util, compute per-holding + sector + portfolio-weighted beta; display in PortfolioRiskMetricsPanel ("Your portfolio moves 1.4x the market")
- [ ] **Enhanced VaR** — add 99% confidence level, dollar amounts, and component VaR decomposition (per-holding contribution to total VaR); extend existing `compute_var_cvar()` + PortfolioRiskMetricsPanel
- [ ] **MCTR (Marginal Contribution to Risk)** — per-holding risk contribution from covariance decomposition; "NVDA contributes 34% of portfolio risk despite being 17% of value"; new MCTRPanel with sorted risk bars in Tier1RiskFeatures
- [ ] **Named historical stress scenarios** — beta-adjusted per-holding impacts for 2008 crash, COVID Mar 2020, 2022 rate hike, dot-com bust; sector ETF proxy when ticker didn't exist; per-holding survivors; new NamedScenarioPanel

## Behavioral

- [ ] **Cooldown** after trim/stop (block re-add N days unless thesis update)
- [ ] **One-line journal** prompt on “Add” from dashboard

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

- [ ] **Cooldown + journal** on trim/add (see Behavioral section)
- [ ] **Calibration curve** on Analysis tab
- [ ] **Catalyst badge** on signals list
- [ ] **Push digest** wired to gates / regime flips

### Do not copy

- Robinhood confetti / gamification (conflicts with decision-support guardrails)
- Webull indicator wall on main screen
- Unusual Whales options flow as default (equity-first product)
- Auto-trade or one-tap buy

---

_Add new items at the bottom; move to **Done** with date when shipped._
