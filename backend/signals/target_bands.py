"""
ST/MT/LT target price bands – ranges, not single numbers.
Uses ATR, volatility, regime, analyst consensus, fundamentals.
"""
from __future__ import annotations

from typing import Any


def _checkpoints(low: float, high: float, n: int = 5) -> list[float]:
    """Generate n evenly spaced price levels between low and high."""
    if n < 2:
        return [round(low, 2), round(high, 2)]
    return [round(low + (high - low) * i / (n - 1), 2) for i in range(n)]


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
             eps_fwd, fair_pe_low, fair_pe_high (optional),
             cons_low, cons_high (optional).
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
    # Trailing re-anchor: when price hits previous target or stop, adjust bands
    ticker = row.get("ticker")
    prev_bands = None
    if ticker:
        try:
            from signals.cache import get_cached_bands
            prev_bands = get_cached_bands(str(ticker))
        except Exception:
            pass

    st_stop = st_target = None
    if prev_bands and isinstance(prev_bands.get("st_band"), dict):
        prev_st = prev_bands["st_band"]
        prev_low = prev_st.get("low")
        prev_high = prev_st.get("high")
        if prev_low is not None and prev_high is not None:
            # Target hit: price closed at/above previous target → trail stop up
            if P >= prev_high:
                st_stop = round(prev_high, 2)  # lock in gains
                st_target = round(P + (atr if atr > 0 else 0.02 * P), 2)
                row["st_level_hit"] = "target"
            # Stop hit: price closed at/below previous stop → full recompute
            elif P <= prev_low:
                st_stop = None  # will compute below
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
    # Optional config override (if user wants manual tweak for specific tickers)
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
                except (TypeError, ValueError):
                    pass
        except Exception:
            pass

    if st_stop is None or st_target is None:
        if st_signal == "BUY":
            st_stop = max(swing_low, P - st_atr_mult_buy * atr) if atr > 0 else P - 0.02 * P
            if P < ma20:
                st_target = ma20
            else:
                st_target = max(swing_high, P + st_atr_mult_buy * atr) if atr > 0 else P + 0.02 * P
        elif st_signal == "SELL":
            st_stop = min(swing_high, P + st_atr_mult_buy * atr) if atr > 0 else P + 0.02 * P
            st_target = min(swing_low, P - st_atr_mult_buy * atr) if atr > 0 else P - 0.02 * P
        else:
            st_stop = P - st_atr_mult_hold * atr if atr > 0 else P - 0.01 * P
            st_target = P + st_atr_mult_hold * atr if atr > 0 else P + 0.01 * P

    row["st_band"] = {"low": round(float(st_stop), 2), "high": round(float(st_target), 2)}
    row["st_checkpoints"] = _checkpoints(float(st_stop), float(st_target), 5)

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

    row["mt_band"] = {"low": round(mt_down, 2), "high": round(mt_up, 2)}

    # ---------- Long-term band (1–3+ yrs) ----------
    eps_fwd = row.get("eps_fwd")
    pe_low = row.get("fair_pe_low")
    pe_high = row.get("fair_pe_high")
    cons_low = row.get("cons_low")
    cons_high = row.get("cons_high")

    fair_low = fair_high = None
    if eps_fwd is not None and pe_low is not None and pe_high is not None:
        try:
            eps_fwd = float(eps_fwd)
            pe_low = float(pe_low)
            pe_high = float(pe_high)
            if eps_fwd > 0:
                fair_low = eps_fwd * pe_low
                fair_high = eps_fwd * pe_high
        except (TypeError, ValueError):
            pass

    if fair_low and fair_high and cons_low is not None and cons_high is not None:
        try:
            cons_low = float(cons_low)
            cons_high = float(cons_high)
            lt_low = min(fair_low * 0.9, cons_low)
            lt_high = max(fair_high * 1.1, cons_high)
            if cons_high > 0 and cons_low > 0 and cons_high / cons_low > 2:
                row["lt_band_low_confidence"] = True
        except (TypeError, ValueError):
            lt_low, lt_high = fair_low, fair_high
    elif fair_low and fair_high:
        lt_low, lt_high = fair_low, fair_high
    elif cons_low is not None and cons_high is not None:
        try:
            lt_low = float(cons_low)
            lt_high = float(cons_high)
        except (TypeError, ValueError):
            lt_low = lt_high = None
    else:
        lt_low = lt_high = None

    if lt_low is not None and lt_high is not None and lt_low < lt_high:
        row["lt_band"] = {"low": round(lt_low, 2), "high": round(lt_high, 2)}
        row["lt_checkpoints"] = _checkpoints(lt_low, lt_high, 5)
        # LT bear/base/bull: bear = low, base = midpoint, bull = high
        mid = (lt_low + lt_high) / 2
        row["lt_scenarios"] = {
            "bear": round(lt_low, 2),
            "base": round(mid, 2),
            "bull": round(lt_high, 2),
        }
    else:
        # Fallback: use MT band scaled for longer horizon when no analyst/consensus data
        mt = row.get("mt_band")
        if isinstance(mt, dict) and mt.get("low") is not None and mt.get("high") is not None:
            mt_low = float(mt["low"])
            mt_high = float(mt["high"])
            lt_low = mt_low * 0.85
            lt_high = mt_high * 1.25
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

    # Cache bands for trailing re-anchor on next run
    if ticker:
        try:
            from signals.cache import set_cached_bands
            bands_to_cache = {
                "st_band": row.get("st_band"),
                "mt_band": row.get("mt_band"),
                "lt_band": row.get("lt_band"),
            }
            if bands_to_cache["st_band"] and bands_to_cache["mt_band"]:
                set_cached_bands(str(ticker), bands_to_cache)
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
