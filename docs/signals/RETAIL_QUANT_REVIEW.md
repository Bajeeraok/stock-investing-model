# Retail Quant Model — Review & Fine-Tuning Guide

This document summarizes a full pass over the retail quant investing app: where to fine-tune the model, how to keep messages crisp and actionable, and what to add so other retail investors can rely on it.

---

## 1. Executive Summary

| Area | Status | Priority |
|------|--------|----------|
| **Model logic** | Solid: composite score, regime, ML-aware signals, 7-layer confidence, rotation step-down | — |
| **Retail messaging** | Good base; some thresholds hardcoded, 65 vs 70 confidence mismatch, ML rules not in tooltips | High |
| **Risk & sizing** | Config-driven 1% risk / 10% stop; tooltip exists in SignalsTable | Low |
| **Persistence** | EOD + paper trades use Redis + DATA_ROOT; forward tracking fixed to use Redis | Done |
| **Actionable alerts** | Entry/exit/duration added for scanner + retail alerts | Done |

**Top actions:** Unify “add when” to one number (70), document ML tiers in config/tooltips, add rotation-risk one-liner, crisp regime/briefing copy, optional config for ML thresholds.

---

## 2. Fine-Tuning the Model

### 2.1 Already configurable (config.yaml)

- **Score:** `score.buy_min` (70), `score.sell_max` (30)
- **Regime:** `regime.up_min` (60), `regime.down_max` (40)
- **Cash deploy:** `cash_deploy_min_score` (70)
- **Risk sizing:** `risk_sizing.risk_pct` (1), `risk_sizing.default_stop_pct` (10)
- **Earnings:** `earnings.days_warning`, `earnings.score_reduction`
- **Overbought:** `overbought.rsi_70_penalty`, etc.

### 2.2 Hardcoded today (candidates for config)

| Location | Current | Suggestion |
|----------|---------|------------|
| **ML-aware signal tiers** | `regime.py`: STRONG BUY 72/55%, BUY 40%, REDUCE/AVOID 20% | Add `score.ml_strong_buy_confluence`, `ml_strong_buy_prob`, `ml_buy_prob`, `ml_avoid_max_prob` (defaults 72, 0.55, 0.40, 0.20) |
| **Portfolio doctor** | `doctor.py`: HOLD/ADD ≥0.65, CONSIDER TRIM &lt;0.45 | Use `cash_deploy_min_score` / 100 or new `portfolio_doctor.add_min_confidence` (0.70) so UI “Add when confidence ≥ 70” matches |
| **Horizon entry** | `horizon_entry_calculator.py`: ST_MIN_ML_PROB 25, MT 35, RSI 35/65 | Add optional `horizon_entry` section in config for power users |
| **Rotation risk** | `breadth_rs.py`: VIX &gt;20/16, real_yield &gt;2.0 | Add optional `rotation_risk` section (vix_high, real_yield_high) |
| **Backtest “OK”** | `backtest_simple.py`: calibration ≥ 70 | Use `score.buy_min` or new `backtest.calibration_ok_min` |

Recommendation: **First** add ML tier defaults to config (and read in `regime.py`) so they’re documented and tunable without code changes. Doctor and horizon constants can follow.

### 2.3 Single source of truth for “model rules”

- **Dashboard** says: “Add only when confidence ≥ 70 and regime UP. Trim when confidence ≤ 30 or regime DOWN.”
- **Portfolio doctor** uses confidence ≥ 0.65 for HOLD/ADD and &lt; 0.45 for CONSIDER TRIM.

Unify to **one** rule set:

- Define in config (e.g. `model_rules.add_min_confidence: 70`, `model_rules.trim_max_confidence: 30`, `model_rules.add_min_regime: UP`).
- Backend: doctor and any “suggestion” logic use these values.
- Frontend: “Model rules” box and tooltips read from the same config (or a small API field `model_rules_summary` built from config).

This removes the 65 vs 70 confusion and keeps retail messaging consistent.

---

## 3. Crisp, Actionable Messages

### 3.1 Regime (Risk-On / Neutral / Risk-Off)

Current (`retail_briefing.py`):

- Risk-On: “Market favors risk-on. Consider small adds on pullbacks; avoid chasing.”
- Neutral: “Mixed signals. Hold core positions; avoid large new buys until clarity.”
- Risk-Off: “Risk-off conditions. Reduce size, tighten stops, avoid new YOLOs.”

Suggested (crisper, same intent):

- **Risk-On:** “Favor small adds on pullbacks. Don’t chase; use your levels.”
- **Neutral:** “Hold core; skip big new buys until the trend is clearer.”
- **Risk-Off:** “Tighten stops, trim size, no new YOLOs. Preserve capital.”

### 3.2 Retail briefing one-liners

- Already actionable: “Stop near $X. Decide: hold or trim.”, “In entry zone $X–$Y. Add small.”, “Wait for pullback to $X–$Y.”
- Small tweak: when score &lt; 35 for holdings, use “Score 34. Trim on strength or tighten stop.” (include the number).
- Non-holders: “Score 65. Consider small add on pullback.” is good; add “Use entry zone and stop from the table.” in the panel hint so users know where to look.

### 3.3 Alerts

- Scanner and retail alerts now have **actionable** text (entry price/date, exit, duration). Keep that pattern for any new alert types.
- For “Covered Call” / “Support Bounce”, the current plain-language blocks are strong; ensure any new metrics (e.g. IV rank) get one sentence of context in the alert body.

### 3.4 Model rules (dashboard)

- One sentence to add after the current “Model rules” line: “Confidence = 7-layer score (regime, pattern, ML, options, insider, fundamental, NLP); open a ticker for breakdown.”
- This ties “confidence ≥ 70” to the 7-layer engine and tells users where to dig deeper.

### 3.5 Rotation risk

- Current: “Rotation risk High = tighten tech buy zones, favor holds.”
- Add a short tooltip or line: “Rotation risk = VIX + real yields + relative strength (e.g. tech vs SPY). High = step down tech adds and favor holds.”

### 3.6 Tooltips (tooltips.yaml)

- **signal:** Today it says “BUY (score>=70), HOLD, SELL (score<=30)” — correct when ML is off. When ML is on, the real logic is confluence + ML tiers.
- Add an **ml_signal** (or extend **signal**) blurb: “With ML: STRONG BUY = confluence ≥72 and ML ≥55%; BUY = confluence ≥65 and ML ≥40%; WATCH = good confluence but ML &lt;40% (wait for confirmation); REDUCE/AVOID when confluence ≤35 or ML &lt;20%.”
- That keeps YAML in sync with `regime.get_ml_aware_signal()` and avoids confusion.

### 3.7 Numbers that need context

- **Confluence (0–100):** Already clarified in SignalsTable as “not a probability”; keep it.
- **ML prob pill:** Already explains “probability of gaining threshold% in 20 days”; keep it.
- **Risk sizing:** SignalsTable tooltip “At X% risk and Y% stop: $Z (~N shares)” is good; ensure it’s visible on hover for the size column.
- **Score label:** “Strong opportunity” / “Extended” come from regime/score; one tooltip on the score column that says “From composite + regime; see Signal for action” is enough.

---

## 4. Cutting-Edge & Reliability (for other retail investors)

### 4.1 Validation visibility

- Forward tracking and backtest results are in the app; consider a small “Model health” strip: last backtest date, calibration OK/Review, forward hit rate (e.g. “ADD 20d hit rate 58%”). That builds trust without overwhelming.

### 4.2 Macro analog

- The “Historically when macro matched current: SPY avg +X% over 3m (Y% green, n=N)” plus plain-language explanation is good. Keep it and ensure it’s visible on the overview.

### 4.3 Do-nothing guidance

- “When macro is Risk-Off or rotation risk is High, consider reducing new buys…” is clear. Optional: add “Avoid new tech adds when rotation risk is High” so it’s explicit for the heaviest users.

### 4.4 Paper trading & EOD

- Paper PnL and forward tracking now use Redis EOD when available; DATA_ROOT is documented for persistence. Optional: in the Paper trading panel, one line “Data stored under DATA_ROOT; set it to a persistent path so history survives restarts” (you already have persistence_note; keep it).

### 4.5 Disclaimers

- Keep “This is context only; past outcomes do not guarantee future results” near macro analog and any backtest/forward-tracking summary so retail investors see it.

### 4.6 Optional future ideas

- **Thesis / exit condition:** Per-position “I will trim if …” and resurface when score/regime changes (see [ANALYSIS_AND_RECOMMENDATIONS.md](../planning/ANALYSIS_AND_RECOMMENDATIONS.md)).
- **Earnings count in header:** “3 holdings with earnings in next 7 days” already considered; ensure it’s visible when &gt; 0.
- **Grey or caution** on signal row when earnings in ≤7 days (IMPROVEMENT_PLAN 5.3).

---

## 5. Implementation Checklist

- [x] EOD from Redis for paper trading and forward tracking
- [x] Actionable alerts (entry/exit/duration)
- [x] Macro analog plain-language explanation
- [ ] **Unify add/trim thresholds:** config + doctor use same numbers; dashboard “Model rules” from config or API
- [ ] **Tooltips:** Add ML-aware signal description to tooltips.yaml
- [ ] **Dashboard:** One-line “Confidence = 7-layer…” and rotation-risk tooltip
- [ ] **Regime / briefing:** Crisp regime lines and optional one-liner tweaks
- [ ] **Config:** Optional ML tier keys (72, 55, 40, 20) with defaults in config.yaml and read in regime.py
- [ ] **Backtest:** Calibration “OK” threshold from config (or score.buy_min)

Doing the checklist items above will make the app more consistent, easier to tune, and more trustworthy for other retail investors.

---

## 6. Morning newsletter (implemented)

A **Morning newsletter** section lives in the **Markets** tab (above Pre-Market Signal Engine). It is built from existing dashboard data and provides a single-place brief:

- **Headline:** "Morning brief · YYYY-MM-DD"
- **Market pulse:** Macro regime + plain-English line; macro analog (SPY 3m historical context); rotation risk.
- **Key levels:** SPY and QQQ with current close, support, and short-term target (from signals).
- **Today's focus:** Earnings count, daily briefing summary, names in entry zone, names near stop.
- **Signal accuracy (20d):** Forward-tracking hit rate by signal (HOLD/ADD, CONSIDER TRIM, etc.) when EOD data exists.
- **Action items:** Crisp bullets (e.g. Risk-Off → reduce buys; rotation High → favor holds; earnings count → avoid new entries; drawdown/concentration nudges; fallback "Add when confidence ≥ 70...").

Backend: `signals/morning_newsletter.py` → `build_morning_newsletter(...)`. Dashboard includes `morning_newsletter` in the response. Frontend: `MorningNewsletter` component in Markets tab; optional **Model health** strip below it showing forward-tracking hit rates in one line.
