"""Single source of truth for the gate/scoring "model version" tag.

Stamped onto EOD signal rows, signal_audit_store events, and paper trade records at the
point each is persisted — so win-rate/accuracy reporting can isolate the current model's
real performance instead of blending it with signals produced under earlier gate/band/
regime logic.

Frozen: do not bump MODEL_VERSION for tuning changes. Each bump split forward tracking
into shards too small to judge (2026.11.1-11.7 shipped in 5 days), so every version from
TRACKING_ERA_SINCE on is scored as one record via tracking_version(). Log tuning changes
in the history below with their date instead. Start a new era only for a rebuild that
makes old calls meaningless, and only with the owner's OK.

History:
- 2026.09.1 — HMM direction-blind |daily_return| feature fix + BEAR-probability floor,
  ST target-band R:R multiplier fix (stop/target no longer symmetric), gates_passed
  sync fix (flat field was clobbered to 0 by readiness_score before this), OBV
  momentum-gate marginal-pass disambiguation.
- 2026.09.2 — momentum_chop pattern-score floor lowered 45 -> 35 (45 sat inside
  pattern_score's documented-normal 27-43 band for non-bottom setups, making the gate
  nearly unreachable — same "flat threshold => ~0% pass rate" failure already fixed once
  for the valuation gate); 35-43 now a marginal pass instead of a hard fail.
- 2026.09.3 — momentum_chop RSI ceiling raised 50 -> 70 (contradicted
  pattern_signals.py::_bullish_trend_score's own "strong trend zone" of RSI 55-70, hard-
  failing every genuine trend-continuation setup regardless of pattern strength); 65-70
  is now a marginal pass. Shipped as its own version (not folded into 2026.09.2) so its
  forward-tracking effect stays attributable even though 2026.09.2 had only ~3-4 EOD
  snapshots of runway first — if either change needs unwinding later, this boundary
  keeps the rollback unambiguous.
- 2026.09.4 — fair-value/target pipeline unification: TTM EPS now excludes anomalously
  large one-time non-operating items (signals/eps_normalization.py) before it drives
  ttm_pe, so a mark-to-market gain no longer makes a stock look artificially cheap;
  medium/long targets now capped by volatility-implied plausibility and analyst-consensus
  proximity (signals/horizon_entry_calculator.py's _plausibility_cap), and the forward-FV
  growth lift's own growth-rate input is capped at 15% instead of 40% (a peg_blend/
  forward_pe fair value already prices growth in once; growing it by the same rate again
  for the 1-year lift was double-counting). Bear case is now derived from a stressed EPS
  x stressed multiple when clean PE/EPS inputs exist, replacing an unexplained flat
  FV x 0.60 on the main path (fair_value_estimator.py::_bear_case). Owner-mode valuation
  label now flags when it disagrees with the horizon's own overall verdict instead of
  reading as an unqualified go-ahead. Paper-trading's headline win-rate stat now counts
  gate_mode=="full_go" rows only (signals/paper_trade_logger.py) — it previously blended
  in starter_only (partial-conviction) rows under the same "accumulate" label, diluting
  the number well below what forward-tracking's own gate-count-vs-win-rate curve implies
  a fully gate-cleared cohort should show. None of this changes gate pass/fail semantics
  themselves, but it changes fair_value, targets, and bear_case materially enough for
  high-growth names that forward-tracking history before this boundary isn't
  apples-to-apples with history after it.
- 2026.10.1 — entry-mode v2: starter_only now requires an actionable zone AND
  at least partial valuation support (was either) after the gate-fail slice audit
  measured -0.65% expectancy on valuation-fail starters (758/1,160 rows); full_go
  additionally opens via market_regime_override when only the stock's own regime
  gate fails while the broad tape is bull, FRED macro is BULL, or the commodity's
  own vol regime is calm — tagged full_go_via for cohort tracking; dip_zone flag
  for the measured score-30-50 edge; IV-rank>75 demotes in-zone starters (knife
  filter). Gate thresholds: REGIME_GATE 60->55, CONFIDENCE_GATE 55->50,
  ST_ML_GATE 25->30; MOS ladder 10/18/25 -> 8/15/22; zone compression
  14/30/45% -> 12/35/50%; score.interpretation force_mean_reverting 2->45 and
  force_trending 0->7 tickers fitted from 21d forward spreads on 148 prod EOD
  snapshots. Forward records before this boundary mix pre/post entry-mode
  semantics — compare cohorts by version, not pooled.
- 2026.10.2 — HOLD by default for chosen stocks: no score-only SELL (low score ->
  HOLD/WATCH, REDUCE only on genuine risk), optional protect mode (half position when
  the stock is below its 200d MA or SPY is risk-off), "stretched / wait for pullback"
  replaced by "above zone, trend intact"; EOD falls back to yfinance when FMP's last
  bar is stale (the 2026-10-26 snapshot carried Friday's closes). Daily latest-model
  scorecard starts here.
- 2026.11.1 — ML horizon odds (1/3/6-month "+N% within H days") come from one pooled
  LightGBM model trained across ~570 S&P 500 stocks on 2000+ history, blended with the
  stock's own since-2000 history odds for the same question (model share 30% for 1-month,
  50% for 3- and 6-month; signals/pooled_odds.py), replacing per-ticker
  models for stocks; crypto, gold/commodity and bond/defensive keep per-ticker models.
  Entry thresholds unchanged. Model-check calls before this boundary are per-ticker odds.
- 2026.11.2 — gold/commodity and bond/defensive ETFs (GLD, SLV, USO, TLT, ...) show their
  own since-2000 history odds instead of per-ticker LightGBM, which was worse than history
  at every horizon in 2019-2026 walk-forward tests and said 97-98% for GLD/SLV 6-month.
  Crypto keeps per-ticker models.
- 2026.11.3 — crypto (BTC-USD, ETH-USD) odds also switch to since-inception history odds;
  their per-ticker models lost to history at 3 and 6 months in 2019-2026 tests. Per-ticker
  LightGBM no longer drives any displayed horizon odds unless history is unavailable.
- 2026.11.7 — Short-term BUY band: stop 2×ATR / ATR target 3×ATR at normal vol (was closer of
  20d swing low and 1.5×ATR, hit first 54% of the time); velocity breakout track is context only.
- 2026.11.6 — Street-anchored fair value falls back to the low analyst target when the median is
  >2.5x the price (stale targets after a drop). SPY intraday 80% ranges refit on 2023-2026 hourly
  data (K 0.40→0.49, width ∝ VIX^1.25); hourly 11:30-15:30 snapshots logged for calibration only.
- 2026.11.5 — When model FV is suppressed and analyst targets are wide, fair value uses the
  analyst median (labelled) instead of the single lowest target.
- 2026.11.4 — Swing (3-month) buy band is capped so its top sits at least 5% under the
  fair-value-capped target (no more bands above their own target); confidence gate is
  advisory (amber, never blocks entries) and header gate counts use the primary gates.
"""

from __future__ import annotations

MODEL_VERSION = "2026.11.7"

# Calls stamped with any version from here on are tracked as one model (MODEL_VERSION).
TRACKING_ERA_SINCE = "2026.11.1"

# First version whose horizon odds come from the pooled model + history blend (signals/pooled_odds.py).
# Model check splits calls at this boundary; later versions changed only non-stock odds.
ODDS_MODEL_SINCE = "2026.11.1"


def _version_key(v: str) -> tuple[int, ...] | None:
    try:
        return tuple(int(x) for x in str(v).split("."))
    except ValueError:
        return None


def tracking_version(version: str | None) -> str | None:
    """Version a call is scored under: MODEL_VERSION for the current era, else as stamped."""
    k = _version_key(version) if version else None
    if k is not None and k >= _version_key(TRACKING_ERA_SINCE):
        return MODEL_VERSION
    return version


def odds_model_is_current(version: str | None) -> bool:
    """True if a call was made by the current horizon-odds model (version >= ODDS_MODEL_SINCE)."""
    k = _version_key(version) if version else None
    return k is not None and k >= _version_key(ODDS_MODEL_SINCE)
