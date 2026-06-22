"""
HMM-based probabilistic regime detection.

Why this beats MA crossovers:
  - MA crossovers are lagging — they confirm the regime AFTER the move
  - HMM learns the statistical fingerprint of each regime from price behaviour
  - Returns soft probabilities: "78% bull, 18% transition, 4% bear"
    rather than a hard label that flips with a single bar

Three hidden states fit naturally to:
  State 0 (bear):       negative mean return, high volatility
  State 1 (transition): near-zero return, moderate volatility
  State 2 (bull):       positive mean return, low-to-moderate volatility

Features (default): [daily_return, |daily_return| (vol proxy), log_volume_change]

Major index ETFs (SPY/QQQ/…): optional **macro** features — first ``hmm_{ticker}_macro.pkl``
(VIX + ^TNX/^IRX yield spread), else ``hmm_{ticker}_vix.pkl`` (VIX only), else price/volume.
Falls back when Yahoo series cannot be aligned.

Model persistence: backend/data/models/hmm_{ticker}.pkl (and hmm_{ticker}_vix.pkl when used)
Graceful degradation: returns None if hmmlearn is not installed.
"""
from __future__ import annotations

import logging
import pickle
import threading
from pathlib import Path

import numpy as np
import pandas as pd

from signals.providers import MAJOR_INDEX_ETFS

logger = logging.getLogger(__name__)

MODELS_DIR = Path(__file__).resolve().parent.parent / "data" / "models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)

# ── In-process model cache ───────────────────────────────────────────────────
# Keeps fitted HMM models in memory so re-calls within the same process skip
# disk I/O and re-fitting entirely. Critical on Railway where the models dir
# may not be writable (save silently fails → every call would re-fit without this).
_MODEL_MEMORY_CACHE: dict[str, object] = {}
_MODEL_FIT_LOCKS: dict[str, threading.Lock] = {}
_MODEL_CACHE_LOCK = threading.Lock()  # protects _MODEL_FIT_LOCKS dict
_HMM_MODEL_CACHE_MAX = 64  # in-memory fitted models; override via HMM_MODEL_CACHE_MAX


def _hmm_cache_max() -> int:
    import os

    raw = (os.environ.get("HMM_MODEL_CACHE_MAX") or "").strip()
    if raw:
        try:
            return max(8, min(256, int(raw)))
        except ValueError:
            pass
    return _HMM_MODEL_CACHE_MAX


def hmm_model_cache_stats() -> dict[str, int]:
    with _MODEL_CACHE_LOCK:
        return {"size": len(_MODEL_MEMORY_CACHE), "max_entries": _hmm_cache_max()}


def trim_hmm_model_cache(*, keep: int | None = None) -> dict[str, int]:
    """Trim in-memory HMM models (disk .pkl still available). keep=0 clears all."""
    cap = _hmm_cache_max() if keep is None else max(0, keep)
    with _MODEL_CACHE_LOCK:
        before = len(_MODEL_MEMORY_CACHE)
        if cap == 0:
            _MODEL_MEMORY_CACHE.clear()
        elif len(_MODEL_MEMORY_CACHE) > cap:
            # dict preserves insertion order (Py3.7+); drop oldest
            while len(_MODEL_MEMORY_CACHE) > cap:
                _MODEL_MEMORY_CACHE.pop(next(iter(_MODEL_MEMORY_CACHE)))
        return {"before": before, "after": len(_MODEL_MEMORY_CACHE), "max_entries": cap}


def _store_hmm_in_cache(cache_key: str, model: object) -> None:
    with _MODEL_CACHE_LOCK:
        _MODEL_MEMORY_CACHE[cache_key] = model
        cap = _hmm_cache_max()
        while len(_MODEL_MEMORY_CACHE) > cap:
            _MODEL_MEMORY_CACHE.pop(next(iter(_MODEL_MEMORY_CACHE)))


def _get_fit_lock(cache_key: str) -> threading.Lock:
    """Return (creating if needed) a per-model lock to prevent concurrent refits."""
    with _MODEL_CACHE_LOCK:
        if cache_key not in _MODEL_FIT_LOCKS:
            _MODEL_FIT_LOCKS[cache_key] = threading.Lock()
        return _MODEL_FIT_LOCKS[cache_key]

# Broad equity index ETFs: HMM on price returns alone lags macro shocks; blend with stress context.
_MAJOR_INDEX_ETF_MACRO = frozenset(MAJOR_INDEX_ETFS) | frozenset({"VOO", "VTI"})

MIN_BARS_TO_FIT = 252   # Need at least 1 year to fit meaningfully
RECENT_BARS     = 60    # Bars used to estimate current regime probability

# Regime sanity thresholds (percent gaps)
# Avoid noise: a tiny -0.4% dip below MA50 should not flip the regime.
MA50_CONFLICT_THRESHOLD_PCT = 1.5   # % below MA50 to trigger conflict
MA200_CONFLICT_THRESHOLD_PCT = 3.0  # % below MA200 to trigger stronger conflict


def validate_regime(
    *,
    ticker: str,
    hmm_dominant: str,  # "BULL" | "TRANSITION" | "BEAR" (optionally "STRONG_BULL")
    last_close: float,
    ma20: float,
    ma50: float,
    ma200: float,
    prev_close: float | None = None,
    prev_ma50: float | None = None,
    days_since_earnings: int | None = None,
    post_earnings_return_pct: float | None = None,
    use_gap_threshold: bool = True,
) -> dict:
    """
    Cross-validate HMM regime against MA structure.

    Returns a dict with:
      - resolved_regime: validated regime to use downstream
      - conflict: whether we overrode / downgraded
      - conflict_severity: LOW | MEDIUM | HIGH
      - gaps and a momentum hint (moving_toward_ma50)

    Designed so we can embed this directly into the HMM payload returned by `get_hmm_regime()`.
    """
    gap_ma50 = (last_close - ma50) / ma50 * 100.0 if ma50 else 0.0
    gap_ma200 = (last_close - ma200) / ma200 * 100.0 if ma200 else 0.0

    prev_gap_ma50 = None
    if prev_close is not None and prev_ma50 not in (None, 0):
        prev_gap_ma50 = (prev_close - float(prev_ma50)) / float(prev_ma50) * 100.0

    gap_trend_ma50 = None
    moving_toward_ma50 = None
    if prev_gap_ma50 is not None:
        gap_trend_ma50 = gap_ma50 - prev_gap_ma50
        # If we were below MA50, "toward" means the gap is getting less negative.
        # If we were above MA50, "toward" means the gap is shrinking.
        moving_toward_ma50 = (abs(gap_ma50) < abs(prev_gap_ma50))

    below_ma50 = gap_ma50 < 0
    below_ma200 = gap_ma200 < 0
    below_ma50_strong = gap_ma50 <= -MA50_CONFLICT_THRESHOLD_PCT if use_gap_threshold else below_ma50
    below_ma200_strong = gap_ma200 <= -MA200_CONFLICT_THRESHOLD_PCT if use_gap_threshold else below_ma200

    above_stack = (last_close > ma50) and (ma50 > ma200)
    strong_bull_stack = (last_close > ma20) and (ma20 > ma50) and (ma50 > ma200)

    ma_regime = (
        "BULL" if above_stack else
        "BEAR" if below_ma200_strong else
        "TRANSITION"
    )

    resolved = hmm_dominant
    conflict = False
    severity = "none"
    reason = None
    note = "HMM and MA agree"

    # ── Post-earnings override ─────────────────────────────────────────────
    # If we're within a short window after earnings and the stock sold off hard
    # AND is meaningfully below MA50, force TRANSITION (HMM can lag post-event).
    post_earnings_override = (
        days_since_earnings is not None
        and days_since_earnings <= 5
        and post_earnings_return_pct is not None
        and post_earnings_return_pct <= -5.0
        and gap_ma50 <= -3.0
        and hmm_dominant in ("BULL", "STRONG_BULL")
    )
    if post_earnings_override:
        resolved = "TRANSITION"
        conflict = True
        severity = "HIGH"
        reason = "POST_EARNINGS_OVERRIDE"
        note = (
            f"Post-earnings override: {abs(gap_ma50):.1f}% below MA50, HMM lagging"
        )

    # If the post-earnings override triggers, keep TRANSITION regardless of MA200.
    if post_earnings_override:
        pass
    elif hmm_dominant == "BULL":
        if ma_regime == "BEAR":
            resolved = "BEAR"
            conflict = True
            severity = "HIGH"
            reason = "HMM_BULL_BUT_BELOW_MA200"
            note = f"HMM overridden: price {gap_ma50:+.2f}% vs MA50"
        elif below_ma50_strong:
            resolved = "TRANSITION"
            conflict = True
            severity = "MEDIUM"
            reason = "HMM_BULL_BUT_BELOW_MA50"
            note = f"HMM overridden: price {gap_ma50:+.2f}% vs MA50"
            # Momentum nuance: if the gap is improving quickly, keep the override but lower severity.
            if gap_trend_ma50 is not None and gap_trend_ma50 >= 0.50:
                severity = "LOW"
        elif below_ma50 and below_ma200:
            # Borderline: below both but within thresholds → do NOT override by default.
            # We only override if the MA200 gap is meaningfully negative.
            if below_ma200_strong:
                resolved = "TRANSITION"
                conflict = True
                severity = "MEDIUM"
                reason = "HMM_BULL_BORDERLINE_BELOW_MAS"
                note = f"HMM overridden: price {gap_ma50:+.2f}% vs MA50"

    elif hmm_dominant == "BEAR":
        if above_stack:
            resolved = "MOMENTUM_EXTENDED" if strong_bull_stack else "TRANSITION"
            conflict = True
            severity = "MEDIUM" if strong_bull_stack else "MEDIUM"
            reason = "HMM_BEAR_BUT_ABOVE_STACK"
            note = (
                f"Momentum extended: price {gap_ma50:+.2f}% vs MA50 with aligned MAs — "
                "HMM mean-reversion signal, not structural bear"
                if strong_bull_stack
                else f"HMM overclaiming Bear: price {gap_ma50:+.2f}% vs MA50"
            )

    elif hmm_dominant == "STRONG_BULL":
        # Not currently emitted by our 3-state HMM, but kept for compatibility if added later.
        if not strong_bull_stack:
            resolved = ma_regime if ma_regime in ("BULL", "TRANSITION") else "TRANSITION"
            conflict = True
            severity = "LOW"
            reason = "HMM_STRONG_BULL_NO_MA_STACK"
            note = "STRONG_BULL downgraded: MA stack not aligned"

    return {
        "resolved_regime": resolved,
        "ma_regime": ma_regime,
        "conflict": conflict,
        "conflict_severity": severity,
        "reason": reason,
        "note": note,
        "gap_ma50_pct": round(gap_ma50, 2),
        "gap_ma200_pct": round(gap_ma200, 2),
        "gap_trend_ma50_pct": round(gap_trend_ma50, 2) if gap_trend_ma50 is not None else None,
        "moving_toward_ma50": moving_toward_ma50,
        "days_since_earnings": days_since_earnings,
        "post_earnings_return_pct": round(float(post_earnings_return_pct), 2) if post_earnings_return_pct is not None else None,
        "strong_bull_stack": strong_bull_stack,
        "above_stack": above_stack,
    }


def detect_momentum_extended(
    *,
    last_close: float,
    ma20: float,
    ma50: float,
    ma200: float,
    high_52w: float | None,
    bull_prob: float,
    bear_prob: float,
    dominant_validated: str,
    gap_ma200_pct: float | None,
    recent_63d_return_pct: float | None,
    rsi: float | None = None,
) -> dict:
    """
    ATH + aligned MAs but low HMM bull % — mean-reversion warning, not structural bear.

    The 3-state HMM labels states by average daily return. Parabolic runs often show
    elevated |return| vol with mixed sign → mass shifts to transition/bear even while
    price makes new highs. Retail copy should say "momentum extended", not "bear".
    """
    above_stack = last_close > ma50 > ma200
    strong_stack = last_close > ma20 > ma50 > ma200
    near_high = (
        high_52w is not None
        and high_52w > 0
        and last_close >= high_52w * 0.94
    )
    extended_run = (
        (recent_63d_return_pct is not None and recent_63d_return_pct >= 12.0)
        or (gap_ma200_pct is not None and gap_ma200_pct >= 18.0)
    )
    low_hmm_bull = bull_prob < 0.42
    elevated_rsi = rsi is not None and rsi >= 58

    active = bool(
        above_stack
        and near_high
        and low_hmm_bull
        and (extended_run or elevated_rsi or strong_stack)
    )

    if not active:
        return {"active": False}

    pct_from_high = (
        round((last_close / high_52w - 1) * 100, 1) if high_52w and high_52w > 0 else None
    )
    note = (
        "Price is at/near 52-week highs with MAs stacked bullish, but HMM assigns "
        f"{round(bull_prob * 100)}% bull — elevated pullback-risk (mean-reversion), "
        "not a broken trend. Gate still blocks new entries until bull % clears."
    )
    return {
        "active": True,
        "label": "Momentum Extended",
        "display_regime": "MOMENTUM_EXTENDED",
        "note": note,
        "pct_from_52w_high": pct_from_high,
        "gap_ma200_pct": gap_ma200_pct,
        "recent_63d_return_pct": recent_63d_return_pct,
        "hmm_bull_pct": round(bull_prob * 100, 1),
        "hmm_bear_pct": round(bear_prob * 100, 1),
        "dominant_validated_before": dominant_validated,
    }


def _adjust_hmm_probs_for_display(
    bull_prob: float,
    transition_prob: float,
    bear_prob: float,
    dominant: str,
    dominant_validated: str,
    conflict: dict | None,
    gap_ma200_pct: float | None,
    recent_63d_return_pct: float | None,
) -> tuple[float, float, float, str | None]:
    """
    Raw HMM bull % is from the latest bar only, while the model is trained on years of data —
    it can stay near-certain "bull" in a name that has already broken down vs MA200.

    When MA validation disagrees (or tape is clearly weak), cap bull and redistribute mass
    so the displayed probabilities match what users see on the chart.
    """
    b, t, r = bull_prob, transition_prob, bear_prob
    note: str | None = None
    cap = 1.0

    if dominant == "BULL":
        if dominant_validated == "BEAR":
            cap = min(cap, 0.38)
            note = "Bull % aligned down vs MA200 (HMM slow vs current stage)"
        elif dominant_validated == "TRANSITION":
            cap = min(cap, 0.55)
            if conflict:
                note = "Bull % tempered to match transition / repair phase"
        if conflict and conflict.get("reason") == "HMM_BULL_BUT_BELOW_MA200":
            cap = min(cap, 0.34)

    if gap_ma200_pct is not None:
        if gap_ma200_pct <= -8.0:
            cap = min(cap, 0.40)
        elif gap_ma200_pct <= -5.0:
            cap = min(cap, 0.48)

    if recent_63d_return_pct is not None:
        if recent_63d_return_pct <= -18.0:
            cap = min(cap, 0.40)
        elif recent_63d_return_pct <= -10.0:
            cap = min(cap, 0.50)

    if b <= cap + 1e-9:
        return b, t, r, note

    freed = b - cap
    b = cap
    if dominant_validated == "BEAR":
        r += freed * 0.55
        t += freed * 0.45
    elif dominant_validated == "TRANSITION":
        t += freed * 0.62
        r += freed * 0.38
    else:
        t += freed * 0.50
        r += freed * 0.50

    s = b + t + r
    if s > 1e-12:
        b, t, r = b / s, t / s, r / s
    return round(b, 3), round(t, 3), round(r, 3), note


def _index_etf_macro_stress(
    close: pd.Series | None,
    vix: float | None,
    recent_63d_return_pct: float | None,
) -> tuple[float, dict]:
    """
    Composite stress 0–1 for major index ETFs from drawdown vs 52w peak, VIX, and 63d return.
    Used to temper price-only HMM bull mass during macro dislocations.
    """
    dbg: dict = {"dd_from_peak_pct": None, "vix": vix, "recent_63d_return_pct": recent_63d_return_pct}
    dd = 0.0
    if close is not None:
        cs = close.dropna()
        if len(cs) >= 60:
            last = float(cs.iloc[-1])
            peak = float(cs.rolling(252, min_periods=60).max().iloc[-1])
            if peak > 0:
                dd = (last / peak - 1.0) * 100.0
                dbg["dd_from_peak_pct"] = round(dd, 2)

    s_dd = min(1.0, max(0.0, (-dd) / 20.0)) * 0.45
    s_vix = 0.0
    if vix is not None and np.isfinite(vix):
        s_vix = min(1.0, max(0.0, (float(vix) - 14.0) / 28.0)) * 0.38
    s_63 = 0.0
    if recent_63d_return_pct is not None and np.isfinite(recent_63d_return_pct):
        s_63 = min(1.0, max(0.0, (-float(recent_63d_return_pct)) / 12.0)) * 0.17

    stress = float(min(1.0, s_dd + s_vix + s_63))
    dbg["components"] = {"s_dd": round(s_dd, 4), "s_vix": round(s_vix, 4), "s_63": round(s_63, 4)}
    return stress, dbg


def _apply_major_index_etf_macro(
    bull: float,
    trans: float,
    bear: float,
    *,
    ticker: str,
    close: pd.Series | None,
    vix: float | None,
    recent_63d_return_pct: float | None,
) -> tuple[float, float, float, dict | None]:
    """Down-weight displayed bull % for index ETFs when macro/price stress is high."""
    tkey = ticker.upper().strip()
    if tkey not in _MAJOR_INDEX_ETF_MACRO:
        return bull, trans, bear, None

    stress, dbg = _index_etf_macro_stress(close, vix, recent_63d_return_pct)
    if stress < 0.07:
        return bull, trans, bear, {"applied": False, "stress": round(stress, 4), **dbg}

    bull_mult = max(0.20, 1.0 - 0.80 * stress)
    new_b = bull * bull_mult
    freed = bull - new_b
    new_t = trans + freed * 0.58
    new_r = bear + freed * 0.42
    s = new_b + new_t + new_r
    if s > 1e-12:
        new_b, new_t, new_r = new_b / s, new_t / s, new_r / s

    audit = {
        "applied": True,
        "stress": round(stress, 4),
        "bull_mult": round(bull_mult, 4),
        **dbg,
        "note": (
            "Major index ETF: HMM blended with VIX / drawdown-from-peak / 63d return — "
            "price-only HMM can stay nominally bull while the tape is stressed"
        ),
    }
    return round(new_b, 3), round(new_t, 3), round(new_r, 3), audit


def _dominant_from_probs(bull: float, trans: float, bear: float) -> str:
    if bull > 0.55:
        return "BULL"
    if bear > 0.55:
        return "BEAR"
    return "TRANSITION"


def _align_vix_series(close: pd.Series) -> pd.Series | None:
    """Align Yahoo ^VIX closes to ``close`` index (equity sessions)."""
    try:
        from signals.fetcher import fetch_ohlcv_safe
    except Exception:
        return None
    try:
        vx = fetch_ohlcv_safe("^VIX", "max")
    except Exception:
        vx = None
    if vx is None or len(vx) < 126:
        return None
    aligned = vx.reindex(close.index).ffill().bfill()
    if aligned.isna().mean() > 0.08:
        return None
    return aligned


def _align_yahoo_yield_series(close: pd.Series, symbol: str) -> pd.Series | None:
    """Align a Yahoo yield series (e.g. ^TNX, ^IRX) to equity ``close`` index."""
    try:
        from signals.fetcher import fetch_ohlcv_safe
    except Exception:
        return None
    try:
        ys = fetch_ohlcv_safe(symbol, "max")
    except Exception:
        ys = None
    if ys is None or len(ys) < 126:
        return None
    aligned = ys.reindex(close.index).ffill().bfill()
    if aligned.isna().mean() > 0.08:
        return None
    return aligned


def _build_features_index_etf_vix(
    close: pd.Series,
    volume: pd.Series | None,
    vix: pd.Series,
) -> np.ndarray | None:
    """
    Same scaling/clipping as :func:`_build_features`, plus VIX daily return and
    rolling z-score of VIX level (126d) for macro stress co-movement with equities.
    """
    ret = close.pct_change().dropna()
    if len(ret) < MIN_BARS_TO_FIT:
        return None
    idx = ret.index
    vx = vix.reindex(close.index).ffill().bfill()
    vix_ret = vx.pct_change().reindex(idx)
    vma = vx.rolling(126, min_periods=40).mean()
    vsd = vx.rolling(126, min_periods=40).std().replace(0, np.nan)
    vix_z = ((vx - vma) / (vsd + 1e-9)).fillna(0.0).reindex(idx)

    feats = [ret.values, np.abs(ret.values)]
    if volume is not None:
        vol_aligned = volume.reindex(idx).ffill().fillna(1)
        log_vol = np.log(vol_aligned.values.clip(1))
        log_vol_change = np.diff(log_vol, prepend=log_vol[0])
        feats.append(log_vol_change)

    feats.append(vix_ret.values.astype(float))
    feats.append(vix_z.values.astype(float))

    arr = np.column_stack(feats)
    mask = np.all(np.isfinite(arr), axis=1)
    arr = arr[mask]
    if len(arr) < MIN_BARS_TO_FIT:
        return None

    std = arr.std(axis=0)
    std[std == 0] = 1.0
    arr = (arr - arr.mean(axis=0)) / std
    arr = np.clip(arr, -4.0, 4.0)
    return arr


def _build_features_index_etf_macro(
    close: pd.Series,
    volume: pd.Series | None,
    vix: pd.Series,
    yield_10y: pd.Series,
    yield_short: pd.Series,
) -> np.ndarray | None:
    """
    VIX features plus 10y–short-rate **spread** level and changes (recession / steepening signal).
    First column remains equity daily return for state ordering in :func:`get_hmm_regime`.
    """
    ret = close.pct_change().dropna()
    if len(ret) < MIN_BARS_TO_FIT:
        return None
    idx = ret.index
    vx = vix.reindex(close.index).ffill().bfill()
    vix_ret = vx.pct_change().reindex(idx)
    vma = vx.rolling(126, min_periods=40).mean()
    vsd = vx.rolling(126, min_periods=40).std().replace(0, np.nan)
    vix_z = ((vx - vma) / (vsd + 1e-9)).fillna(0.0).reindex(idx)

    y10 = yield_10y.reindex(close.index).ffill().bfill()
    ys = yield_short.reindex(close.index).ffill().bfill()
    spread = (y10 - ys).reindex(close.index).ffill().bfill()
    spread_d = spread.diff().reindex(idx)
    sma = spread.rolling(126, min_periods=40).mean()
    ssd = spread.rolling(126, min_periods=40).std().replace(0, np.nan)
    spread_z = ((spread - sma) / (ssd + 1e-9)).fillna(0.0).reindex(idx)

    feats = [ret.values, np.abs(ret.values)]
    if volume is not None:
        vol_aligned = volume.reindex(idx).ffill().fillna(1)
        log_vol = np.log(vol_aligned.values.clip(1))
        log_vol_change = np.diff(log_vol, prepend=log_vol[0])
        feats.append(log_vol_change)

    feats.extend(
        [
            vix_ret.values.astype(float),
            vix_z.values.astype(float),
            spread_d.values.astype(float),
            spread_z.values.astype(float),
        ]
    )

    arr = np.column_stack(feats)
    mask = np.all(np.isfinite(arr), axis=1)
    arr = arr[mask]
    if len(arr) < MIN_BARS_TO_FIT:
        return None

    std = arr.std(axis=0)
    std[std == 0] = 1.0
    arr = (arr - arr.mean(axis=0)) / std
    arr = np.clip(arr, -4.0, 4.0)
    return arr


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_hmm_regime(
    ticker: str,
    close: pd.Series,
    volume: pd.Series | None = None,
    force_refit: bool = False,
    most_recent_earnings_date: str | None = None,
    days_since_earnings: int | None = None,
    post_earnings_return_pct: float | None = None,
    post_earnings_volume_ratio: float | None = None,
    vix: float | None = None,
) -> dict | None:
    """
    Fit (or load) a 3-state HMM and return current regime probabilities.

    Returns:
        {
          "bull_probability":       float,   # 0-1
          "transition_probability": float,
          "bear_probability":       float,
          "dominant_state":         str,     # "BULL" | "TRANSITION" | "BEAR"
          "state_means":            list[float],   # mean daily return per state
          "n_bars_fit":             int,
          "error":                  str | None,
        }
    or None if hmmlearn is not installed.
    """
    try:
        from hmmlearn.hmm import GaussianHMM  # noqa: F401
    except ImportError:
        logger.debug("hmmlearn not installed — HMM regime unavailable")
        return None

    if close is None or len(close) < MIN_BARS_TO_FIT:
        return _error_result(f"Need {MIN_BARS_TO_FIT}+ bars; got {len(close) if close is not None else 0}")

    tkey = ticker.upper().strip()
    features: np.ndarray | None = None
    model_suffix = ""
    used_augmented_hmm = False
    if tkey in _MAJOR_INDEX_ETF_MACRO:
        vx_ser = _align_vix_series(close)
        y10 = _align_yahoo_yield_series(close, "^TNX")
        yshort = _align_yahoo_yield_series(close, "^IRX")
        if vx_ser is not None and y10 is not None and yshort is not None:
            fm = _build_features_index_etf_macro(close, volume, vx_ser, y10, yshort)
            if fm is not None and len(fm) >= MIN_BARS_TO_FIT:
                features = fm
                model_suffix = "_macro"
                used_augmented_hmm = True
        if features is None and vx_ser is not None:
            fv = _build_features_index_etf_vix(close, volume, vx_ser)
            if fv is not None and len(fv) >= MIN_BARS_TO_FIT:
                features = fv
                model_suffix = "_vix"
                used_augmented_hmm = True
    if features is None:
        features = _build_features(close, volume)
    if features is None or len(features) < MIN_BARS_TO_FIT:
        return _error_result("Could not build HMM features")

    model = _load_or_fit(ticker, features, force_refit, model_suffix=model_suffix)
    if model is None:
        return _error_result("HMM fit failed")

    # Predict probabilities on the most recent window
    recent = features[-RECENT_BARS:]
    try:
        state_probs = model.predict_proba(recent)   # shape (n_bars, 3)
        current_probs = state_probs[-1]             # latest bar
    except Exception as exc:
        return _error_result(f"HMM predict failed: {exc}")

    # Identify which state index = bull / bear / transition by mean return
    means = model.means_[:, 0]   # first feature = daily return
    order = np.argsort(means)    # lowest mean first
    # order[0] = bear, order[1] = transition, order[2] = bull

    bear_idx       = int(order[0])
    transition_idx = int(order[1])
    bull_idx       = int(order[2])

    bear_prob       = float(current_probs[bear_idx])
    transition_prob = float(current_probs[transition_idx])
    bull_prob       = float(current_probs[bull_idx])

    dominant = (
        "BULL"       if bull_prob > 0.55 else
        "BEAR"       if bear_prob > 0.55 else
        "TRANSITION"
    )

    # Cross-check against observable MA structure (sanity guard).
    # Uses % gap thresholds to avoid flip-flopping on marginal dips (e.g., -0.4% below MA50).
    dominant_validated = dominant
    conflict = None
    gap_ma200_pct: float | None = None
    try:
        if close is not None and len(close) >= 200:
            close_s = close.dropna()
            if len(close_s) >= 200:
                last_close = float(close_s.iloc[-1])
                ma20 = float(close_s.rolling(20, min_periods=20).mean().iloc[-1])
                ma50 = float(close_s.rolling(50, min_periods=50).mean().iloc[-1])
                ma200 = float(close_s.rolling(200, min_periods=200).mean().iloc[-1])
                prev_close = float(close_s.iloc[-2]) if len(close_s) >= 2 else None
                prev_ma50 = (
                    float(close_s.rolling(50, min_periods=50).mean().iloc[-2])
                    if len(close_s) >= 51
                    else None
                )
                v = validate_regime(
                    ticker=ticker,
                    hmm_dominant=dominant,
                    last_close=last_close,
                    ma20=ma20,
                    ma50=ma50,
                    ma200=ma200,
                    prev_close=prev_close,
                    prev_ma50=prev_ma50,
                    days_since_earnings=days_since_earnings,
                    post_earnings_return_pct=post_earnings_return_pct,
                    use_gap_threshold=True,
                )

                dominant_validated = v["resolved_regime"]
                gap_ma200_pct = float(v["gap_ma200_pct"])
                if v["conflict"]:
                    conflict = {
                        "reason": v["reason"],
                        "severity": v["conflict_severity"],
                        "note": v["note"],
                        "gap_ma50_pct": v["gap_ma50_pct"],
                        "gap_ma200_pct": v["gap_ma200_pct"],
                        "gap_trend_ma50_pct": v["gap_trend_ma50_pct"],
                        "moving_toward_ma50": v["moving_toward_ma50"],
                        "days_since_earnings": v["days_since_earnings"],
                        "post_earnings_return_pct": v["post_earnings_return_pct"],
                        "last_close": round(last_close, 2),
                        "ma50": round(ma50, 2),
                        "ma200": round(ma200, 2),
                    }
                    logger.info(
                        "[hmm] %s regime conflict: dominant=%s → validated=%s (close=%.2f ma50=%.2f ma200=%.2f) [gap_ma50=%+.2f%% severity=%s]",
                        ticker,
                        dominant,
                        dominant_validated,
                        last_close,
                        ma50,
                        ma200,
                        float(v["gap_ma50_pct"]),
                        v["conflict_severity"],
                    )
    except Exception:
        pass

    recent_63d_return_pct: float | None = None
    try:
        if close is not None:
            cs = close.dropna()
            if len(cs) >= 65:
                last = float(cs.iloc[-1])
                prev = float(cs.iloc[-64])
                if prev > 0:
                    recent_63d_return_pct = (last / prev - 1.0) * 100.0
    except Exception:
        pass

    if gap_ma200_pct is None and close is not None:
        try:
            cs = close.dropna()
            if len(cs) >= 200:
                last_close = float(cs.iloc[-1])
                ma200 = float(cs.rolling(200, min_periods=200).mean().iloc[-1])
                if ma200 > 0:
                    gap_ma200_pct = (last_close - ma200) / ma200 * 100.0
        except Exception:
            pass

    bull_adj, tr_adj, br_adj, display_note = _adjust_hmm_probs_for_display(
        bull_prob,
        transition_prob,
        bear_prob,
        dominant,
        dominant_validated,
        conflict,
        gap_ma200_pct,
        recent_63d_return_pct,
    )

    if used_augmented_hmm:
        bull_fin, tr_fin, br_fin = bull_adj, tr_adj, br_adj
        spec = "VIX + yield-curve spread (^TNX−^IRX)" if model_suffix == "_macro" else "VIX-augmented"
        macro_audit = {
            "applied": False,
            "note": (
                f"{spec} HMM features for index ETF — post-hoc macro blend skipped "
                "to avoid double-counting stress"
            ),
        }
    else:
        bull_fin, tr_fin, br_fin, macro_audit = _apply_major_index_etf_macro(
            bull_adj,
            tr_adj,
            br_adj,
            ticker=ticker,
            close=close,
            vix=vix,
            recent_63d_return_pct=recent_63d_return_pct,
        )
    dominant_display = _dominant_from_probs(bull_fin, tr_fin, br_fin)

    momentum_extended: dict = {"active": False}
    ma20_val: float | None = None
    high_52w: float | None = None
    rsi_val: float | None = None
    try:
        if close is not None:
            cs = close.dropna()
            if len(cs) >= 20:
                ma20_val = float(cs.rolling(20, min_periods=20).mean().iloc[-1])
            if len(cs) >= 60:
                high_52w = float(cs.rolling(252, min_periods=60).max().iloc[-1])
            if len(cs) >= 20:
                try:
                    import ta

                    rsi_s = ta.momentum.RSIIndicator(cs).rsi()
                    rv = float(rsi_s.iloc[-1])
                    if rv == rv:
                        rsi_val = rv
                except Exception:
                    pass
            if len(cs) >= 200 and gap_ma200_pct is None:
                last_close = float(cs.iloc[-1])
                ma200_v = float(cs.rolling(200, min_periods=200).mean().iloc[-1])
                if ma200_v > 0:
                    gap_ma200_pct = (last_close - ma200_v) / ma200_v * 100.0
            if len(cs) >= 50 and ma20_val is not None:
                last_close = float(cs.iloc[-1])
                ma50_v = float(cs.rolling(50, min_periods=50).mean().iloc[-1])
                ma200_v = float(cs.rolling(200, min_periods=200).mean().iloc[-1])
                momentum_extended = detect_momentum_extended(
                    last_close=last_close,
                    ma20=ma20_val,
                    ma50=ma50_v,
                    ma200=ma200_v,
                    high_52w=high_52w,
                    bull_prob=bull_fin,
                    bear_prob=br_fin,
                    dominant_validated=dominant_validated,
                    gap_ma200_pct=gap_ma200_pct,
                    recent_63d_return_pct=recent_63d_return_pct,
                    rsi=rsi_val,
                )
                if momentum_extended.get("active"):
                    dominant_display = "MOMENTUM_EXTENDED"
                    if dominant_validated in ("BEAR", "TRANSITION"):
                        dominant_validated = "MOMENTUM_EXTENDED"
    except Exception:
        pass

    # One-step transition matrix row for "transition" state — direction of next bar if latent state were transition
    transition_next: dict | None = None
    try:
        tm = getattr(model, "transmat_", None)
        if tm is not None and getattr(tm, "shape", None) == (3, 3):
            row = np.asarray(tm[transition_idx], dtype=float)
            rs = float(row.sum())
            if rs > 0:
                row = row / rs
            pb = float(row[bull_idx])
            pe = float(row[bear_idx])
            pt = float(row[transition_idx])
            exit_mass = pb + pe
            transition_next = {
                "p_next_bull": round(pb, 4),
                "p_next_bear": round(pe, 4),
                "p_next_transition": round(pt, 4),
            }
            if exit_mass > 1e-9:
                transition_next["p_exit_to_bull"] = round(pb / exit_mass, 4)
                transition_next["p_exit_to_bear"] = round(pe / exit_mass, 4)
    except Exception:
        transition_next = None

    hmm_shift_direction: dict | None = None
    try:
        from signals.hmm_regime_shift_direction import (
            build_ui_payload,
            compute_shift_direction_semantic,
        )

        tm = getattr(model, "transmat_", None)
        if tm is not None and getattr(tm, "shape", None) == (3, 3):
            pi_model = np.zeros(3, dtype=float)
            pi_model[bull_idx] = bull_fin
            pi_model[transition_idx] = tr_fin
            pi_model[bear_idx] = br_fin
            ps = float(pi_model.sum())
            if ps > 1e-12:
                pi_model = pi_model / ps
            raw_sd = compute_shift_direction_semantic(
                tm,
                pi_model,
                bull_idx,
                transition_idx,
                bear_idx,
                horizon_days=10,
            )
            if raw_sd:
                hmm_shift_direction = {**build_ui_payload(raw_sd), "detail": raw_sd}
    except Exception:
        hmm_shift_direction = None

    return {
        "bull_probability":       bull_fin,
        "transition_probability": tr_fin,
        "bear_probability":       br_fin,
        "bull_probability_raw":    round(bull_prob, 3),
        "display_adjustment_note": display_note,
        "index_etf_macro":       macro_audit,
        "hmm_feature_spec": (
            "index_macro_vix_yield"
            if model_suffix == "_macro"
            else "index_vix_augmented"
            if model_suffix == "_vix"
            else "price_volume"
        ),
        "recent_63d_return_pct": round(recent_63d_return_pct, 2) if recent_63d_return_pct is not None else None,
        "gap_ma200_pct":          round(gap_ma200_pct, 2) if gap_ma200_pct is not None else None,
        "dominant_state":         dominant_display,
        "dominant_state_model_raw": dominant,
        "dominant_state_validated": dominant_validated,
        "momentum_extended":      momentum_extended if momentum_extended.get("active") else None,
        "ma_conflict":           conflict,
        "earnings_context": {
            "most_recent_earnings_date": most_recent_earnings_date,
            "days_since_earnings": days_since_earnings,
            "post_earnings_return_pct": round(float(post_earnings_return_pct), 2) if post_earnings_return_pct is not None else None,
            "post_earnings_volume_ratio": round(float(post_earnings_volume_ratio), 2) if post_earnings_volume_ratio is not None else None,
        },
        "state_means_daily_ret":  [round(float(means[i]), 5) for i in order],
        "n_bars_fit":             len(features),
        "transition_next":      transition_next,
        "hmm_shift_direction":  hmm_shift_direction,
        "error":                  None,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_features(close: pd.Series, volume: pd.Series | None) -> np.ndarray | None:
    """
    Build standardised [daily_return, |daily_return|, log_vol_change] feature matrix.

    Features are z-score standardised AND clipped to ±4σ before fitting.
    Clipping removes flash-crash outliers (e.g. -20% in a single day) that
    cause extreme Gaussian likelihoods, destabilise the EM covariance update,
    and produce the "Model is not converging" log warning.
    """
    ret = close.pct_change().dropna()
    if len(ret) < MIN_BARS_TO_FIT:
        return None

    feats = [ret.values, np.abs(ret.values)]

    if volume is not None:
        vol_aligned = volume.reindex(ret.index).ffill().fillna(1)
        log_vol = np.log(vol_aligned.values.clip(1))
        log_vol_change = np.diff(log_vol, prepend=log_vol[0])
        feats.append(log_vol_change)

    arr = np.column_stack(feats)
    # Remove rows with NaN / inf (can appear at boundaries)
    mask = np.all(np.isfinite(arr), axis=1)
    arr = arr[mask]

    # Standardise each feature to zero-mean unit-variance so the EM algorithm
    # treats each dimension equally — without this the return column (~0.001 scale)
    # and vol-change column (~0.1 scale) have very different magnitudes.
    std = arr.std(axis=0)
    std[std == 0] = 1.0   # avoid division by zero for constant features
    arr = (arr - arr.mean(axis=0)) / std

    # Clip to ±4σ (post-standardisation so ±4 means ±4 std-devs).
    # Flash crashes / circuit-breaker days sit 8-15σ away from the mean and
    # pull the Gaussian means toward the tail, causing EM to step backwards.
    arr = np.clip(arr, -4.0, 4.0)

    return arr


def _model_path(ticker: str, *, suffix: str = "") -> Path:
    return MODELS_DIR / f"hmm_{ticker.upper()}{suffix}.pkl"


def _load_or_fit(
    ticker: str,
    features: np.ndarray,
    force_refit: bool,
    *,
    model_suffix: str = "",
) -> object | None:
    import warnings
    import logging as _std_logging
    from hmmlearn.hmm import GaussianHMM

    path = _model_path(ticker, suffix=model_suffix)
    cache_key = f"{ticker.upper()}{model_suffix}"
    n_features = int(features.shape[1])

    # ── 1. Check in-process memory cache first ───────────────────────────────
    # Avoids disk I/O and re-fitting on every call within the same process.
    # Critical on Railway where data/models may not be writable.
    if not force_refit and cache_key in _MODEL_MEMORY_CACHE:
        mem_model = _MODEL_MEMORY_CACHE[cache_key]
        mem_means = getattr(mem_model, "means_", None)
        if mem_means is not None and int(getattr(mem_means, "shape", [0, 0])[1]) == n_features:
            return mem_model
        # Dimension changed since last fit — drop stale in-memory entry
        _MODEL_MEMORY_CACHE.pop(cache_key, None)

    # ── 2. Serialise to one fit per ticker at a time ─────────────────────────
    fit_lock = _get_fit_lock(cache_key)
    with fit_lock:
        # Re-check memory cache after acquiring the lock (another thread may have just fitted)
        if not force_refit and cache_key in _MODEL_MEMORY_CACHE:
            mem_model = _MODEL_MEMORY_CACHE[cache_key]
            mem_means = getattr(mem_model, "means_", None)
            if mem_means is not None and int(getattr(mem_means, "shape", [0, 0])[1]) == n_features:
                return mem_model

        # ── 3. Try loading from disk ─────────────────────────────────────────
        if path.exists() and not force_refit:
            try:
                with open(path, "rb") as f:
                    cached = pickle.load(f)
                means = getattr(cached, "means_", None)
                if means is not None and getattr(means, "shape", None):
                    if int(means.shape[1]) != n_features:
                        logger.info(
                            "HMM cached model %s dim %d vs features %d — deleting stale pkl and refitting",
                            path.name, means.shape[1], n_features,
                        )
                        # Delete stale file so future process starts don't reload wrong dims
                        try:
                            path.unlink(missing_ok=True)
                        except Exception:
                            pass
                    else:
                        _store_hmm_in_cache(cache_key, cached)
                        return cached
                else:
                    _store_hmm_in_cache(cache_key, cached)
                    return cached
            except Exception:
                logger.debug("HMM cache corrupt for %s — refitting", ticker)
                try:
                    path.unlink(missing_ok=True)
                except Exception:
                    pass

        # ── 4. Fit a fresh model ─────────────────────────────────────────────
        # Fit on all bars except last RECENT_BARS to avoid future peeking
        train = features[:-RECENT_BARS] if len(features) > RECENT_BARS + 100 else features

        # Silence hmmlearn's logger during fitting
        _hmm_log = _std_logging.getLogger("hmmlearn")
        _hmm_prev_level = _hmm_log.level
        _hmm_log.setLevel(_std_logging.CRITICAL)

        best_model, best_score = None, -np.inf
        for seed in (42, 7, 123, 17, 99):
            try:
                candidate = GaussianHMM(
                    n_components=3,
                    covariance_type="diag",
                    n_iter=500,
                    random_state=seed,
                    tol=1e-3,
                    min_covar=1e-2,
                )
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    candidate.fit(train)
                score = candidate.score(train)
                if score > best_score:
                    best_score, best_model = score, candidate
            except Exception as exc:
                logger.debug("HMM fit attempt seed=%s failed for %s: %s", seed, ticker, exc)

        _hmm_log.setLevel(_hmm_prev_level)

        if best_model is None:
            logger.warning("All HMM fit attempts failed for %s", ticker)
            return None

        # Store in memory cache immediately — even if disk save fails, subsequent
        # calls within this process skip re-fitting entirely.
        _store_hmm_in_cache(cache_key, best_model)

        try:
            with open(path, "wb") as f:
                pickle.dump(best_model, f)
            logger.info("HMM model %s fitted and saved (dim=%d)", path.name, n_features)
        except Exception as e:
            logger.warning(
                "HMM model %s fitted but disk save failed (%s) — cached in memory only",
                path.name, e,
            )

        return best_model


def _error_result(msg: str) -> dict:
    return {
        "bull_probability":       0.5,
        "transition_probability": 0.3,
        "bear_probability":       0.2,
        "dominant_state":         "TRANSITION",
        "state_means_daily_ret":  [],
        "n_bars_fit":             0,
        "error":                  msg,
    }
