"""
ST/MT/LT target price bands – ranges, not single numbers.
Uses ATR, volatility, regime, analyst consensus, fundamentals.
"""
from __future__ import annotations

from typing import Any

from .band_context import lt_dispersion_multiplier, symmetric_widen
from .cache import TTL_TARGET_BANDS, get_cached_bands, set_cached_bands
from .providers import MAJOR_INDEX_ETFS

# Max relative drift of cached ST band center vs spot to trust trailing (index ETFs = tighter bands)
_MAX_CENTER_DRIFT_INDEX_ETF = 0.09
_MAX_CENTER_DRIFT_DEFAULT = 0.18

# LT band upside leg: the fair-value pipeline (signals/fair_value_pipeline.py) returns a single
# point estimate (plus an optional bear_case), not a bull case — this multiplier is a documented,
# tunable default for the missing upside leg, not derived from the estimator itself. Paired with
# the 0.75x synthetic bear leg below (the same ratio fair_value_pipeline.py itself already uses
# for its own bear_case whenever it sets one) for a 35% total spread — matching, not exceeding,
# _cap_band_width_for_display's 35%-of-spot LT cap, so a ticker trading near fair value gets an
# uncapped, genuinely fv-derived band instead of always hitting the display cap.
LT_BULL_MULTIPLIER = 1.10
# Fallback downside leg when the pipeline didn't supply fair_value_bear_case.
_LT_SYNTHETIC_BEAR_MULT = 0.75


def _checkpoints(low: float, high: float, n: int = 5) -> list[float]:
    """Generate n evenly spaced price levels between low and high."""
    if n < 2:
        return [round(low, 2), round(high, 2)]
    return [round(low + (high - low) * i / (n - 1), 2) for i in range(n)]


def _prev_st_band_near_spot(P: float, prev_bands: dict | None, ticker: str | None) -> bool:
    """
    Use cached band only if its center is near today's spot (avoids stale trailing).
    Index ETFs (SPY/QQQ/DIA/IWM) use a tighter threshold — e.g. 14% drift must reject (was passing 18%).
    """
    if not prev_bands or not isinstance(prev_bands.get("st_band"), dict):
        return False
    pl = prev_bands["st_band"].get("low")
    ph = prev_bands["st_band"].get("high")
    if pl is None or ph is None or P <= 0:
        return False
    try:
        lo, hi = float(pl), float(ph)
    except (TypeError, ValueError):
        return False
    if lo >= hi:
        return False
    mid = 0.5 * (lo + hi)
    tkey = str(ticker).upper() if ticker else ""
    max_drift = _MAX_CENTER_DRIFT_INDEX_ETF if tkey in MAJOR_INDEX_ETFS else _MAX_CENTER_DRIFT_DEFAULT
    return abs(mid - P) / P <= max_drift


def _band_cache_ttl_seconds(daily_move_pct: float | None) -> int:
    """
    Shorter Redis TTL on large daily moves so pre-crash bands (e.g. SLV) expire faster.
    |move| > 5% -> 4h; > 2% -> 12h; else 24h max.
    """
    if daily_move_pct is None:
        return TTL_TARGET_BANDS
    try:
        a = abs(float(daily_move_pct))
    except (TypeError, ValueError):
        return TTL_TARGET_BANDS
    if a > 5.0:
        return 4 * 3600
    if a > 2.0:
        return 12 * 3600
    return TTL_TARGET_BANDS


def _st_band_brackets_spot(P: float, st_low: float, st_high: float) -> bool:
    """ST band should straddle spot (stop below, target above) for retail display."""
    if st_low >= st_high or P <= 0:
        return False
    pad = P * 0.015
    return (st_low - pad) <= P <= (st_high + pad)


def _reset_st_band_around_spot(P: float, atr: float, vol6: float) -> tuple[float, float]:
    """Symmetric band when prior math left spot outside [st_low, st_high]."""
    mult = 1.0 + min(0.5, max(0.0, vol6 - 0.35) * 2) if vol6 > 0.35 else 1.0
    w = max(atr * mult, 0.012 * P) if atr > 0 else 0.015 * P
    return P - w, P + w


def _cap_band_width_for_display(
    low: float,
    high: float,
    *,
    spot: float,
    band_key: str,
    anchor: float | None = None,
) -> tuple[float, float, bool]:
    """
    Cap very wide MT/LT display bands so they remain decision-useful.
    Wide ranges can look like weak model confidence and become non-actionable.

    anchor: point the capped window must stay centered on (LT: fair value). Without it the
    window kept the LOW end — a deep stress-tail low then produced bands like AVGO
    $123–$240 that excluded both spot ($334) and fair value ($508).
    """
    if not (spot > 0 and high > low > 0):
        return low, high, False
    width_pct = (high - low) / spot
    max_pct_by_band = {
        "st": 0.18,
        "mt": 0.30,
        "lt": 0.35,
    }
    cap = max_pct_by_band.get(str(band_key).lower(), 0.30)
    if width_pct <= cap:
        return low, high, False
    width = spot * cap
    if anchor is not None and low <= anchor <= high:
        new_low = max(low, anchor - width / 2)
        new_high = min(high, new_low + width)
        new_low = max(low, new_high - width)
        return round(new_low, 2), round(new_high, 2), True
    new_high = low + width
    min_pad = max(0.01, spot * 0.002)
    new_high = max(min(new_high, high), low + min_pad)
    return round(low, 2), round(new_high, 2), True


def _st_signal_from_suggestion(sugg: str | None) -> str:
    """Map short_suggestion to BUY/SELL/HOLD for band logic."""
    if not sugg:
        return "HOLD"
    s = str(sugg).upper()
    if "ADD" in s or "BUY" in s:
        return "BUY"
    if "TRIM" in s or "SELL" in s:
        return "SELL"
    return "HOLD"


def add_target_bands(row: dict[str, Any]) -> dict[str, Any]:
    """
    Add st_band, mt_band, lt_band to a ticker row.
    Expects: price, ma20, atr14, regime, vol_6m, short_suggestion,
             swing_high_20d, swing_low_20d (optional),
             fair_value, fair_value_bear_case, fair_value_suppressed (optional — from
             signals/fair_value_pipeline.py; LT band is built from these, not an
             independent PE/consensus blend),
             cons_low, cons_high, consensus_median, eps_dispersion (optional, FMP — feed
             lt_dispersion_multiplier's street-target-spread widening only, not the point
             estimate itself),
             band_event_multiplier (optional, 1.0 — widen ST/MT near CPI/FOMC week).
             daily_move_pct (optional) — prior close to last close % move; shortens band-cache TTL when large.
    """
    P = row.get("price") or row.get("close")
    if P is None:
        row["st_band"] = None
        row["mt_band"] = None
        row["lt_band"] = None
        return row

    P = float(P)
    atr = row.get("atr14") or row.get("atr_14") or 0
    if atr is not None:
        atr = float(atr)
    else:
        atr = 0
    ma20 = row.get("ma20", P)
    if ma20 is not None:
        ma20 = float(ma20)
    else:
        ma20 = P
    regime = row.get("regime", "NEUTRAL")
    vol6 = row.get("vol_6m", 0.3)
    if vol6 is not None:
        vol6 = float(vol6)
    else:
        vol6 = 0.3
    st_signal = _st_signal_from_suggestion(row.get("short_suggestion"))

    swing_high = row.get("swing_high_20d")
    swing_low = row.get("swing_low_20d")
    if swing_high is None:
        swing_high = max(P, ma20)
    else:
        swing_high = float(swing_high)
    if swing_low is None:
        swing_low = min(P, ma20)
    else:
        swing_low = float(swing_low)

    # ---------- Short-term band (days–weeks) ----------
    # Optional trailing from Redis (TTL 4–24h by daily move): target/stop hit → re-anchor.
    ticker = row.get("ticker")
    prev_bands = None
    if ticker:
        try:
            prev_bands = get_cached_bands(str(ticker))
        except Exception:
            pass
    if prev_bands and not _prev_st_band_near_spot(P, prev_bands, ticker):
        prev_bands = None

    st_stop = st_target = None
    if prev_bands and isinstance(prev_bands.get("st_band"), dict):
        prev_st = prev_bands["st_band"]
        prev_low = prev_st.get("low")
        prev_high = prev_st.get("high")
        if prev_low is not None and prev_high is not None:
            if P >= float(prev_high):
                st_stop = round(float(prev_high), 2)
                st_target = round(P + (atr if atr > 0 else 0.02 * P), 2)
                row["st_level_hit"] = "target"
            elif P <= float(prev_low):
                st_stop = None
                row["st_level_hit"] = "stop"

    # Auto-adjust band width by volatility: high-vol tickers get wider bands (better accuracy without manual config)
    # vol6 = 6m annualized vol (e.g. 0.3 = 30%). Above 35% we scale up: 0.4->1.6, 0.5->1.8, 0.6+->2.0
    base_mult_buy = 1.5
    base_mult_hold = 1.0
    if vol6 > 0.35:
        extra = min(0.5, (vol6 - 0.35) * 2)
        base_mult_buy = 1.5 + extra
        base_mult_hold = 1.0 + extra
    st_atr_mult_buy = base_mult_buy
    st_atr_mult_hold = base_mult_hold
    # Target-side multiplier for directional (BUY/SELL) calls only — a HOLD/neutral band
    # makes no directional claim, so it stays symmetric. A BUY/SELL band asserts an edge,
    # so its target distance should exceed its stop distance by this multiple; without it,
    # target = stop distance and R:R lands at ~1.0 regardless of setup quality (empirically
    # confirmed: 14/17 real watchlist tickers landed at exactly 1.0 before this fix).
    RR_TARGET_MULTIPLE = 1.5
    st_atr_mult_target = st_atr_mult_buy * RR_TARGET_MULTIPLE
    # Optional config override (if user wants manual tweak for specific tickers) — an
    # explicit per-ticker override means "use this exact multiplier symmetrically", so it
    # replaces the RR widening rather than stacking with it.
    if ticker:
        try:
            from config_loader import load_config
            cfg = load_config()
            overrides = (cfg.get("accuracy") or {}).get("st_target_atr_mult_overrides") or {}
            if isinstance(overrides, dict) and ticker in overrides:
                try:
                    mult = float(overrides[ticker])
                    if mult > 0:
                        st_atr_mult_buy = mult
                        st_atr_mult_hold = mult
                        st_atr_mult_target = mult
                except (TypeError, ValueError):
                    pass
        except Exception:
            pass

    if st_stop is None or st_target is None:
        if st_signal == "BUY":
            st_stop = max(swing_low, P - st_atr_mult_buy * atr) if atr > 0 else P - 0.02 * P
            atr_target = P + st_atr_mult_target * atr if atr > 0 else P + 0.03 * P
            st_target = max(swing_high, atr_target, ma20) if P < ma20 else max(swing_high, atr_target)
        elif st_signal == "SELL":
            st_stop = min(swing_high, P + st_atr_mult_buy * atr) if atr > 0 else P + 0.02 * P
            atr_target = P - st_atr_mult_target * atr if atr > 0 else P - 0.03 * P
            st_target = min(swing_low, atr_target)
        else:
            st_stop = P - st_atr_mult_hold * atr if atr > 0 else P - 0.01 * P
            st_target = P + st_atr_mult_hold * atr if atr > 0 else P + 0.01 * P

    # Ensure low <= high for display (SELL mode: stop > target, so normalize)
    st_low = min(float(st_stop), float(st_target))
    st_high = max(float(st_stop), float(st_target))
    # Clamp to 52w range when available
    range_low = row.get("range_52w_low")
    range_high = row.get("range_52w_high")
    if range_low is not None and range_high is not None and range_low <= range_high:
        st_low = max(st_low, float(range_low))
        st_high = min(st_high, float(range_high))

    ev_m = float(row.get("band_event_multiplier") or 1.0)
    if ev_m > 1.001 and st_high > st_low:
        st_low, st_high = symmetric_widen(st_low, st_high, ev_m)
        if range_low is not None and range_high is not None and range_low <= range_high:
            st_low = max(st_low, float(range_low))
            st_high = min(st_high, float(range_high))

    if not _st_band_brackets_spot(P, st_low, st_high):
        st_low, st_high = _reset_st_band_around_spot(P, atr, vol6)
        row["st_band_sanity_reset"] = True

    row["st_band"] = {"low": round(st_low, 2), "high": round(st_high, 2)}
    row["st_checkpoints"] = _checkpoints(float(st_low), float(st_high), 5)

    # ---------- Medium-term band (months) ----------
    if regime == "UP":
        mt_down = P * (1 - 0.3 * vol6)
        mt_up = P * (1 + 0.5 * vol6)
    elif regime == "DOWN":
        mt_down = P * (1 - 0.5 * vol6)
        mt_up = P * (1 + 0.3 * vol6)
    else:
        mt_down = P * (1 - 0.4 * vol6)
        mt_up = P * (1 + 0.4 * vol6)

    mt_low = round(mt_down, 2)
    mt_high = round(mt_up, 2)
    if range_low is not None and range_high is not None and range_low <= range_high:
        mt_low = max(mt_low, float(range_low))
        mt_high = min(mt_high, float(range_high))

    if ev_m > 1.001 and mt_high > mt_low:
        mt_low, mt_high = symmetric_widen(float(mt_low), float(mt_high), ev_m)
        if range_low is not None and range_high is not None and range_low <= range_high:
            mt_low = max(mt_low, float(range_low))
            mt_high = min(mt_high, float(range_high))
        mt_low = round(mt_low, 2)
        mt_high = round(mt_high, 2)

    mt_low, mt_high, mt_capped = _cap_band_width_for_display(
        float(mt_low), float(mt_high), spot=P, band_key="mt"
    )
    if mt_capped:
        row["mt_band_width_capped"] = True

    row["mt_band"] = {"low": mt_low, "high": mt_high}

    # ---------- Long-term band (1–3+ yrs) ----------
    # Anchored on the single shared fair-value pipeline (signals/fair_value_pipeline.py, also
    # used by api/ticker_detail.py) instead of an independent PE-band blend — previously two
    # unrelated fair-value numbers could disagree by 20%+ for the same ticker/day depending on
    # which surface (Signals table vs ticker-detail modal) you looked at.
    fv = row.get("fair_value")
    bear_case = row.get("fair_value_bear_case")

    lt_low = lt_high = None
    if fv is not None:
        try:
            fv = float(fv)
        except (TypeError, ValueError):
            fv = None
    if fv is not None and fv > 0:
        try:
            lt_low = float(bear_case) if bear_case is not None and float(bear_case) > 0 else fv * _LT_SYNTHETIC_BEAR_MULT
        except (TypeError, ValueError):
            lt_low = fv * _LT_SYNTHETIC_BEAR_MULT
        lt_high = fv * LT_BULL_MULTIPLIER
        # fv is a point estimate, not necessarily inside [lt_low, lt_high] once bear_case/the
        # bull multiplier are applied — the band must always contain it.
        lt_low = min(lt_low, fv)
        lt_high = max(lt_high, fv)

    if lt_low is not None and lt_high is not None and lt_low < lt_high:
        # "Don't fully trust this number" analog for the new source: the pipeline suppressed
        # a real model estimate (banks/REITs/biotech/etc.) and anchored to street consensus
        # instead — replaces the old analyst-consensus-dispersion signal this flag used to mean.
        if row.get("fair_value_suppressed"):
            row["lt_band_low_confidence"] = True
        # Long-horizon stress bear: ensure bear reflects historical tail risk (10+yr monthly)
        stress_bear_pct = row.get("stress_bear_pct")
        if stress_bear_pct is not None and P > 0 and stress_bear_pct > 0:
            stress_bear_price = P * (1 - stress_bear_pct / 100)
            lt_low = min(lt_low, stress_bear_price)
        lt_m, lt_note = lt_dispersion_multiplier(row)
        if lt_m > 1.001:
            lt_low, lt_high = symmetric_widen(float(lt_low), float(lt_high), lt_m)
            if lt_note:
                row["lt_band_dispersion_note"] = lt_note
        # fv IS the point estimate the valuation gate wants — no more averaging a blended range.
        row["lt_fair_value_mid"] = round(fv, 2)
        tail_low = float(lt_low)
        lt_low, lt_high, lt_capped = _cap_band_width_for_display(
            float(lt_low), float(lt_high), spot=P, band_key="lt", anchor=fv
        )
        if lt_capped:
            row["lt_band_width_capped"] = True
            # Keep the stress tail visible separately — the displayed band centers on FV.
            row["lt_tail_low"] = round(tail_low, 2)
        row["lt_band"] = {"low": round(lt_low, 2), "high": round(lt_high, 2)}
        row["lt_checkpoints"] = _checkpoints(lt_low, lt_high, 5)
        # LT bear/base/bull: bear = the real downside tail (not the re-centered display edge),
        # base = midpoint, bull = high
        mid = (lt_low + lt_high) / 2
        bear = round(min(lt_low, tail_low), 2)
        base_val, bull = round(mid, 2), round(lt_high, 2)
        row["lt_scenarios"] = {"bear": bear, "base": base_val, "bull": bull}
        # Low confidence when bull is far above base (>50% of base)
        if base_val > 0 and abs(bull - base_val) > 0.5 * base_val:
            row["lt_band_low_confidence"] = row.get("lt_band_low_confidence", False) or True
    else:
        # Fallback: use MT band scaled for longer horizon when no analyst/consensus data
        mt = row.get("mt_band")
        if isinstance(mt, dict) and mt.get("low") is not None and mt.get("high") is not None:
            mt_low = float(mt["low"])
            mt_high = float(mt["high"])
            lt_low = mt_low * 0.85
            lt_high = mt_high * 1.25
            # Long-horizon stress bear: anchor bear level to historical tail risk
            stress_bear_pct = row.get("stress_bear_pct")
            if stress_bear_pct is not None and P > 0 and stress_bear_pct > 0:
                stress_bear_price = P * (1 - stress_bear_pct / 100)
                lt_low = min(lt_low, stress_bear_price)
            lt_m, lt_note = lt_dispersion_multiplier(row)
            if lt_m > 1.001:
                lt_low, lt_high = symmetric_widen(float(lt_low), float(lt_high), lt_m)
                if lt_note:
                    row["lt_band_dispersion_note"] = lt_note
            row["lt_fair_value_mid"] = round((float(lt_low) + float(lt_high)) / 2, 2)
            lt_low, lt_high, lt_capped = _cap_band_width_for_display(
                float(lt_low), float(lt_high), spot=P, band_key="lt"
            )
            if lt_capped:
                row["lt_band_width_capped"] = True
            row["lt_band"] = {"low": round(lt_low, 2), "high": round(lt_high, 2)}
            row["lt_checkpoints"] = _checkpoints(lt_low, lt_high, 5)
            row["lt_scenarios"] = {
                "bear": round(lt_low, 2),
                "base": round((lt_low + lt_high) / 2, 2),
                "bull": round(lt_high, 2),
            }
            row["lt_band_low_confidence"] = True  # no analyst data
        else:
            row["lt_band"] = None
            row["lt_checkpoints"] = None
            row["lt_scenarios"] = None
            row["lt_fair_value_mid"] = None

    # Backtest-based confidence for ST/MT targets (from regime × ATR-distance hit-rate table)
    try:
        from .target_confidence import get_target_confidence, load_hit_rates_table
        _table = load_hit_rates_table()
        _st_band = row.get("st_band")
        _mt_band = row.get("mt_band")
        if _st_band and _st_band.get("high") is not None:
            _conf = get_target_confidence(regime, P, float(_st_band["high"]), atr, "st", _table)
            if _conf is not None:
                row["st_target_confidence_pct"] = _conf
        if _mt_band and _mt_band.get("high") is not None:
            _conf = get_target_confidence(regime, P, float(_mt_band["high"]), atr, "mt", _table)
            if _conf is not None:
                row["mt_target_confidence_pct"] = _conf
    except Exception:
        pass

    # Cache for next run — TTL shorter on high-vol days (see _band_cache_ttl_seconds)
    if ticker:
        try:
            bands_to_cache = {
                "st_band": row.get("st_band"),
                "mt_band": row.get("mt_band"),
                "lt_band": row.get("lt_band"),
            }
            if bands_to_cache["st_band"] and bands_to_cache["mt_band"]:
                ttl = _band_cache_ttl_seconds(row.get("daily_move_pct"))
                set_cached_bands(str(ticker), bands_to_cache, ttl_seconds=ttl)
        except Exception:
            pass

    return row


def compute_vol_6m(close) -> float | None:
    """6-month realized volatility (annualized). Needs 126+ days of close."""
    if close is None or len(close) < 126:
        return None
    import numpy as np
    returns = close.pct_change().dropna().iloc[-126:]
    if len(returns) < 60:
        return None
    std = float(returns.std())
    return round(std * (252 ** 0.5), 4)


def compute_swing_high_low(close, window: int = 20) -> tuple[float | None, float | None]:
    """Swing high/low from close (proxy when high/low not available)."""
    if close is None or len(close) < window:
        return None, None
    subset = close.iloc[-window:]
    return float(subset.max()), float(subset.min())
