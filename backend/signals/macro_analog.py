"""
Macro analog: correlate current macro state (VIX + real yield) with historical states
and return a one-liner: "Historically when similar: SPY avg +X% over 3m (Y% green)."
Uses 13y of VIX, real yield proxy, and SPY history.
"""
from __future__ import annotations

import logging

import pandas as pd

logger = logging.getLogger(__name__)

# VIX buckets: low <15, medium 15-20, high 20-25, very_high >25
# Real yield buckets: low <1, medium 1-2, high >2


def _vix_bucket(v: float | None) -> str:
    if v is None:
        return "unknown"
    if v < 15:
        return "low"
    if v < 20:
        return "medium"
    if v < 25:
        return "high"
    return "very_high"


def _real_yield_bucket(r: float | None) -> str:
    if r is None:
        return "unknown"
    if r < 1:
        return "low"
    if r < 2:
        return "medium"
    return "high"


def _load_vix_history(period: str = "13y") -> pd.Series | None:
    from .fetcher import fetch_ohlcv_safe
    close = fetch_ohlcv_safe("^VIX", period)
    return close


def _load_spy_history(period: str = "13y") -> pd.Series | None:
    from .fetcher import fetch_ohlcv_safe
    close = fetch_ohlcv_safe("SPY", period)
    return close


def _load_real_yield_history(config: dict, start_date: str, end_date: str) -> pd.Series | None:
    from .fred_client import fetch_series_range, get_api_key
    if not get_api_key(config):
        return None
    nom, _ = fetch_series_range(config, "DGS10", start_date, end_date)
    infl, _ = fetch_series_range(config, "T10YIE", start_date, end_date)
    if not nom or not infl:
        return None
    def _parse_vals(obs: list) -> pd.DataFrame:
        rows = []
        for o in obs:
            v = o.get("value")
            if v is None or v == ".":
                continue
            try:
                rows.append({"date": o["date"], "val": float(v)})
            except (TypeError, ValueError):
                continue
        return pd.DataFrame(rows)

    nom_df = _parse_vals(nom)
    nom_df = nom_df.rename(columns={"val": "nom"})
    infl_df = _parse_vals(infl)
    infl_df = infl_df.rename(columns={"val": "infl"})
    if nom_df.empty or infl_df.empty:
        return None
    merged = pd.merge(nom_df[["date", "nom"]], infl_df[["date", "infl"]], on="date", how="inner")
    merged["date"] = pd.to_datetime(merged["date"])
    merged["real"] = merged["nom"] - merged["infl"]
    merged = merged.dropna(subset=["real"])
    if merged.empty:
        return None
    return merged.set_index("date")["real"]


def get_macro_analog(
    vix_current: float | None,
    real_yield_current: float | None,
    config: dict | None = None,
    period: str = "13y",
) -> dict | None:
    """
    Match current VIX + real yield to historical states; return one-liner stats.
    Returns { state, n_observations, avg_return_3m, pct_positive, one_liner } or None.
    """
    config = config or {}
    vix = _load_vix_history(period)
    spy = _load_spy_history(period)
    if vix is None or spy is None or len(vix) < 252 or len(spy) < 252:
        return None

    vix = vix.sort_index()
    spy = spy.sort_index()
    spy_idx = spy.index
    start_d = spy_idx.min()
    end_d = spy_idx.max()
    if hasattr(start_d, "date"):
        start_str = start_d.date().isoformat() if hasattr(start_d, "date") else str(start_d)[:10]
    else:
        start_str = str(start_d)[:10]
    if hasattr(end_d, "date"):
        end_str = end_d.date().isoformat()
    else:
        end_str = str(end_d)[:10]

    real_yield_hist = _load_real_yield_history(config, start_str, end_str)

    # Align VIX and SPY on common index
    common_idx = vix.index.intersection(spy.index).sort_values()
    if len(common_idx) < 200:
        return None

    # 3-month forward return (approx 63 trading days)
    fwd_days = 63
    returns_3m = spy.pct_change(fwd_days).shift(-fwd_days)

    # Align real yield to SPY index (forward-fill)
    ry_aligned = None
    if real_yield_hist is not None and not real_yield_hist.empty:
        try:
            ry_aligned = real_yield_hist.reindex(common_idx).ffill()
        except Exception:
            pass

    rows = []
    for i, dt in enumerate(common_idx):
        if i + fwd_days >= len(spy):
            continue
        try:
            v = float(vix.loc[dt])
        except Exception:
            v = None
        if pd.isna(v):
            v = None
        try:
            ret = returns_3m.loc[dt]
        except Exception:
            ret = None
        if pd.isna(ret) or ret is None:
            continue
        ry = None
        if ry_aligned is not None and dt in ry_aligned.index and pd.notna(ry_aligned.loc[dt]):
            try:
                ry = float(ry_aligned.loc[dt])
            except Exception:
                pass
        vix_b = _vix_bucket(v)
        ry_b = _real_yield_bucket(ry)
        state = f"VIX_{vix_b}"
        if ry_b != "unknown":
            state += f"_RY_{ry_b}"
        rows.append({"state": state, "ret_3m": ret * 100, "green": 1 if ret > 0 else 0})

    if len(rows) < 50:
        return None

    df = pd.DataFrame(rows)
    state_stats = df.groupby("state").agg(
        n=("ret_3m", "count"),
        avg_return_3m=("ret_3m", "mean"),
        pct_positive=("green", "mean"),
    ).reset_index()
    state_stats["pct_positive"] = (state_stats["pct_positive"] * 100).round(1)
    state_stats["avg_return_3m"] = state_stats["avg_return_3m"].round(2)

    # Match current state
    vix_b = _vix_bucket(vix_current)
    ry_b = _real_yield_bucket(real_yield_current)
    state_match = f"VIX_{vix_b}"
    if ry_b != "unknown":
        state_match += f"_RY_{ry_b}"
    match_row = state_stats[state_stats["state"] == state_match]
    if len(match_row) == 0:
        state_match = f"VIX_{vix_b}"
        match_row = state_stats[state_stats["state"] == state_match]
    if len(match_row) == 0:
        return None

    row = match_row.iloc[0]
    n = int(row["n"])
    if n < 20:
        return {
            "state": state_match,
            "n_observations": n,
            "avg_return_3m": float(row["avg_return_3m"]),
            "pct_positive": float(row["pct_positive"]),
            "one_liner": f"Limited historical analog (n={n}); mixed outcomes.",
        }

    avg = float(row["avg_return_3m"])
    pct = float(row["pct_positive"])
    sign = "+" if avg >= 0 else ""
    one_liner = f"Historically when macro matched current: SPY avg {sign}{avg}% over 3m ({pct:.0f}% green, n={n})."
    return {
        "state": state_match,
        "n_observations": n,
        "avg_return_3m": avg,
        "pct_positive": pct,
        "one_liner": one_liner,
    }
