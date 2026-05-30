# Rotation Risk, Next-Day Bias & Confidence: Gap Analysis & Recommendations

This document compares your spec (breadth/rotation, pre-market, next-day outlook, target confidence) against the current codebase and suggests what to build, what to skip, and what to do better.

---

## 1. What You Already Have (Summary)

| Spec area | Current implementation | Location |
|-----------|------------------------|----------|
| **Regime** | UP / NEUTRAL / DOWN from composite score; Risk-On / Neutral / Risk-Off macro banner from VIX + real yield | `signals/regime.py`, `api/routers/dashboard.py` (macro_regime), `Dashboard.tsx` |
| **Cross-asset** | DXY, GLD, USO, VIX, 10Y; guidelines (DXY+GLD, VIX+GLD, real yield, heavy macro week) | `signals/cross_asset.py`, `GuidelinesBanner` |
| **ST/MT/LT bands** | ATR-based ST stop/target; vol_6m + regime for MT; analyst/consensus for LT; trailing re-anchor on target/stop hit | `signals/target_bands.py`, `run_daily.py`, ticker detail |
| **ATR & vol** | 14d ATR proxy (std × price), 6m realized vol; used in bands and risk sizing | `run_daily.py`, `target_bands.compute_vol_6m` |
| **Backtest** | Score buckets vs 1/3/6m forward returns (hit rate, avg return); ST/MT band “target vs stop first” calibration | `backtest_simple.py`, `backtest_targets.py` |
| **Confidence (2026 picks)** | Heuristic: regime + score + sector; not backtest-based | `best_picks.py` |
| **LT band confidence** | Boolean “low confidence” when analyst dispersion high or no analyst data | `target_bands.py` (lt_band_low_confidence), TickerDetailModal |
| **Sector context** | Sector ETF (XLK, XLF, etc.) for benchmark; sector in best picks | `signals/providers.py` (_SECTOR_ETF), `best_picks.py` |

So you already have: **regime, cross-asset rules, ATR/vol, target bands, and backtests for score buckets and for ST/MT hit vs stop**. You do **not** yet have: breadth, tech leadership/RS, rotation risk label, pre-market snapshot, next-day bias/typical move, or **per-level** backtest-based confidence for ST/MT/LT.

---

## 2. Spec vs Reality: Detailed Gap Map

### 2.1 End-of-day breadth + leadership (day before)

| Spec item | Status | Notes |
|-----------|--------|--------|
| % S&P 500 above 20/50-day MA | ❌ Missing | Need constituent list + EOD prices for ~500 names; FMP or another source. |
| % XLK / NDX / QQQ components above 20/50-day MA | ❌ Missing | Same: need component lists + history. |
| Advance/decline, new highs/new lows (NASDAQ, S&P) | ❌ Missing | Usually from exchange/aggregator (e.g. NYSE, Nasdaq); not in current stack. |
| Relative strength: XLK vs SPY, QQQ vs SPY | ❌ Missing | You have sector ETF mapping but no RS line or “rolling over” detection. |
| Equal-weight tech vs cap-weight tech | ❌ Missing | Would need RSP vs SPY and a tech equal-weight proxy (or custom basket). |
| “Tech rotation risk: elevated” badge | ❌ Missing | Depends on breadth + RS above. |
| Overextension + narrow leadership (index high, breadth weak) | ❌ Missing | Would consume breadth + index level. |

**Data reality:**  
- **Breadth (% above MA):** Requires either (a) a provider that gives breadth pre-computed (e.g. some paid APIs / charting vendors), or (b) S&P 500 / NDX / XLK constituent lists plus EOD for each. FMP has index constituents; you’d need to fetch many symbols (rate limits/cost).  
- **A/D, new highs/lows:** Often from dedicated breadth data (e.g. StockCharts, Barchart, or institutional feeds). Not standard in FMP/yfinance.  
- **RS lines:** You already fetch SPY, QQQ, XLK. RS = ratio of closes (e.g. XLK/SPY); “rolling over” = short-term trend of that ratio (e.g. 5–10d slope or MA cross). No new data source needed.

**Recommendation:**  
- **Do first (no new data):** Add **relative strength** for XLK/SPY and QQQ/SPY (and optionally XLF, XLE, XLI vs SPY). Compute ratio, then 5d/10d slope or simple “RS rising / flat / falling” from MAs on the ratio. Use this + existing VIX/real yield to define a **“Tech leadership: strong / weakening / falling”** and a simple **“Rotation risk: low / medium / high”** (e.g. high when RS rolling over + VIX elevated or real yield high).  
- **Add later (if you get breadth data):** % above 20/50-day MA for one index (e.g. S&P 500) and use it to set “Market breadth: strong / neutral / weak” and to elevate rotation risk when “index near highs but breadth weak.”

### 2.2 Pre-market regime snapshot (same morning)

| Spec item | Status | Notes |
|-----------|--------|--------|
| ES / NQ futures vs fair value | ❌ Missing | Need futures data (e.g. ES=F, NQ=F from yfinance, or a futures API). |
| Pre-market movers: mega-cap tech (AAPL, MSFT, …) and XLF, XLE, XLI | ❌ Missing | Need pre-market quotes; yfinance can have extended-hours; FMP may have pre-market. |
| Pre-market banner: “Futures soft; mega-cap red, value flat/green → rotation risk high” | ❌ Missing | Depends on above. |

**Data reality:**  
- **Futures:** yfinance symbols like `ES=F`, `NQ=F` often give overnight/pre-market; need to validate and align with “vs prior close” or “vs fair value” (fair value needs cash index + funding).  
- **Pre-market quotes:** yfinance `history(period="1d", interval="1m")` or similar can include pre-market; FMP has pre-market in some plans. Batch quote at 9:00–9:20 ET would need a scheduled job or on-demand call.

**Recommendation:**  
- **Phase 1:** Add an optional **pre-market module** that runs on a schedule (or on dashboard load before open): fetch ES=F, NQ=F and a small basket (e.g. AAPL, MSFT, META, NVDA, NFLX, TSLA, XLF, XLE, XLI) and compute change vs prior close. If NQ underperforms ES and mega-cap tech is red while value/cyclicals flat or green, set a **pre-market rotation risk** flag and show a one-line banner.  
- **Phase 2:** If you add EOD breadth/rotation risk, combine: “EOD: rotation risk high; Pre-market: futures soft, tech red → tighten tech buy zones.”

### 2.3 Integration: global banner and per-ticker rules

| Spec item | Status | Notes |
|-----------|--------|--------|
| Global banner: “Market breadth / Tech leadership / Rotation risk” | ⚠️ Partial | You have “Macro regime: Risk-On/Neutral/Risk-Off” and guidelines. No breadth/tech leadership/rotation row yet. |
| When rotation risk HIGH: tighten ST buy zones for tech, ADD→HOLD, require deeper pullback | ❌ Missing | Bands and suggestions are regime-aware but not rotation-risk or sector-aware. |

**Recommendation:**  
- Add a **Market / Sector Regime** row (or extend the macro banner): **Market breadth:** Strong / Neutral / Weak (from breadth when available; else “—”), **Tech leadership:** Rising / Flat / Falling (from RS), **Rotation risk:** Low / Medium / High.  
- When **rotation risk = High**, in the same place you compute `short_suggestion` / `medium_suggestion`: for tickers in a “tech” sector, step down one notch (ADD→HOLD, HOLD→CONSIDER TRIM) and optionally require a deeper pullback (e.g. larger ATR multiple for “buy zone”) before showing ADD. You already have sector in `get_sector_and_industry`; use it in `run_daily` or in a small post-pass.

### 2.4 Green-day / red-day “prediction” and typical move range

| Spec item | Status | Notes |
|-----------|--------|--------|
| State (trend, momentum, vol) → historical next-day P(up), avg return, std | ❌ Missing | Would need state definition + 3–5y history and forward returns. |
| “Next-day bias: 58% odds of green, avg move +0.3% / –0.4%” | ❌ Missing | Same. |
| Typical 1-day range from σ₁ (realized vol), ±1σ, high-vol regime ±1.8% | ⚠️ Partial | You have vol_6m and ATR; no explicit “typical 1-day range” or regime-conditioned vol for SPY/QQQ/GLD/SLV. |
| Next-Day Outlook row for SPY, QQQ, GLD, SLV (bias + expected move) | ❌ Missing | No such block. |

**Recommendation:**  
- **Typical move range:** Easy add. For SPY, QQQ, GLD, SLV (and any index/ETF you care about), compute 20d or 60d realized σ of daily returns, then show “Typical 1-day range: ±X%” (e.g. ±1σ) and optionally “In high-vol regime: ±Y%” using a simple vol regime (e.g. VIX > 20 or 20d vol > 90th percentile). Reuse `compute_vol_6m`-style logic but 1d vol and optionally regime split.  
- **Next-day bias:** Add a small **state → history** backtest: define state (e.g. above/below 20/50 MA, RSI zone, vol regime), bucket historical days, compute next-day P(green) and avg up/down move. Expose for SPY, QQQ, GLD, SLV as “Next-day bias: Bullish/Neutral/Bearish (e.g. 58% green); typical range ±X%.” This is honest and useful without pretending exact prediction.

### 2.5 Confidence scores for ST/MT/LT levels (backtest-based)

| Spec item | Status | Notes |
|-----------|--------|--------|
| “Hit” = target or stop hit first within horizon (intraday high/low) | ⚠️ Partial | `backtest_targets.py` uses **close** vs target/stop, not intraday high/low. Spec asks for intraday. |
| Probability buckets by asset type, regime, target distance (ATR) | ❌ Missing | Backtest is global target_hit_pct / stop_hit_pct; no buckets by distance or regime. |
| Daily confidence: look up hit-rate for current distance bucket | ❌ Missing | No per-level confidence shown in UI. |
| “ST target $X (conf: 68% over 20d)” | ❌ Missing | Tooltip says “ATR-based; MA20/swing context” but no numeric confidence. |
| Recompute hit-rate tables monthly | ❌ Missing | Backtest is on-demand; no stored tables. |

**Recommendation:**  
- **Intraday hit:** If you have OHLC (not just close), change `backtest_targets` to “target hit if high ≥ target before low ≤ stop” (and same for stop). That matches the spec and is more realistic.  
- **Buckets:** In backtest, group by (a) regime, (b) distance of target from price in ATR (e.g. 0–1, 1–2, 2–3× ATR). Produce a small table: regime × distance_bucket → hit_rate, avg time to hit. Store as JSON (e.g. `data/target_hit_rates.json`); refresh monthly or on-demand.  
- **Daily confidence:** When you compute st_band/mt_band, compute distance in ATR to target (and optionally to stop), look up the corresponding bucket’s hit_rate, and attach e.g. `st_target_confidence_pct`, `mt_target_confidence_pct` to the row. Show in UI: “ST target $X (conf: 68% over 20d).”  
- **Wording:** Add disclaimer: “Confidence is based on how often similar targets were hit in the past under similar conditions; it is not a guarantee.”

---

## 3. Better or Additional Features to Consider

- **Single breadth proxy with minimal data:** If full S&P 500 breadth is costly, use **RSP (equal-weight S&P) vs SPY** as a cheap proxy: when SPY makes new highs but RSP is lagging, participation is narrowing. You already have ETF fetchers; add RSP and compare 20/50d trend of SPY vs RSP.  
- **VIX term structure (optional):** Contango vs backwardation as “risk-on vs risk-off” nuance; you already use VIX level. Can add later.  
- **Rotation risk and sector tilt:** When rotation risk is High, optionally **highlight** sectors with improving RS (e.g. XLF, XLE, XLI) in the opportunities or “2026 picks” view, not only “tighten tech.”  
- **Next-day and 5-day:** Implement next-day bias first; if useful, add 5-day horizon with same state-based historical stats.  
- **Correlation to existing work:** Breadth/RS and rotation risk feed the same “Market / Sector Regime” row and the same per-ticker step-down (ADD→HOLD for tech when rotation high). Pre-market then reinforces that same label before the open.

---

## 4. Suggested Implementation Order

1. **RS + rotation risk (no new breadth data)**  
   - Compute XLK/SPY and QQQ/SPY RS (ratio, then short-term trend).  
   - Define Tech leadership: Rising / Flat / Falling.  
   - Define Rotation risk: Low / Medium / High (RS + VIX + real yield).  
   - Add Market/Sector Regime row to dashboard; when Rotation risk = High, step down tech suggestions (ADD→HOLD, deeper pullback for buy zone).

2. **Typical move range**  
   - For SPY, QQQ, GLD, SLV: 20d/60d realized σ, show “Typical 1-day range ±X%” and optionally high-vol regime range.

3. **Next-day bias (state-based)**  
   - Backtest state → next-day P(green), avg return.  
   - Expose “Next-day bias” and “Typical range” for SPY, QQQ, GLD, SLV in a small “Next-Day Outlook” block.

4. **Pre-market snapshot (optional)**  
   - ES/NQ + basket vs prior close; pre-market rotation line when tech red, value flat/green.

5. **Breadth (when data exists)**  
   - Add % above 20/50-day MA for one index (e.g. S&P 500) and “Market breadth: Strong/Neutral/Weak”; optionally RSP/SPY as cheap proxy first.

6. **ST/MT/LT confidence from backtest**  
   - Intraday hit in backtest; bucket by regime + ATR distance; store hit-rate table; attach confidence to bands and show in UI with disclaimer.

This order gets you “tech rotation / market wobble” flags and honest probability framing with minimal new data, then layers on pre-market and breadth when feasible, and finally makes target confidence explicit and backtest-based.

---

## 5. Implementation Summary (Done)

- **`backend/signals/breadth_rs.py`**: RS ratios (XLK/SPY, QQQ/SPY, RSP/SPY), tech leadership, market breadth label, rotation risk; `apply_rotation_step_down()` for tech tickers when rotation risk is High.
- **`backend/signals/typical_move.py`**: Typical 1-day range for SPY, QQQ, GLD, SLV; optional high-vol regime.
- **`backend/signals/next_day_bias.py`**: State-based backtest; next-day P(green), avg return, typical range; Bullish/Neutral/Bearish bias.
- **`backend/signals/premarket.py`**: ES/NQ and tech vs value/cyclicals basket; pre-market rotation risk and message.
- **`backend/signals/target_confidence.py`**: Regime x ATR-distance hit-rate table; ST/MT confidence when table exists.
- **`backend/scripts/build_target_hit_rates.py`**: Builds `data/target_hit_rates.json`. Run monthly: `cd backend && python scripts/build_target_hit_rates.py`.
- **Dashboard API**: Returns `market_regime`, `next_day_outlook`, `typical_move`, `pre_market`; applies rotation step-down.
- **Frontend**: Market/Sector Regime row; pre-market banner; Next-Day Outlook and Typical move; ST/MT confidence in TickerDetailModal.
