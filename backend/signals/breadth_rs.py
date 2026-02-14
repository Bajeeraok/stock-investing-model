"""
Market breadth proxy, relative strength (XLK/SPY, QQQ/SPY), and rotation risk.
No constituent-level breadth; uses RS lines and optional RSP/SPY for participation.
"""
from __future__ import annotations

import pandas as pd

from .fetcher import fetch_ohlcv_safe


def _rs_ratio(leader: pd.Series, benchmark: pd.Series) -> pd.Series | None:
    """Align and compute leader/benchmark ratio. Returns series with common index."""
    if leader is None or benchmark is None or len(leader) < 20 or len(benchmark) < 20:
        return None
    common = leader.index.intersection(benchmark.index)
    if len(common) < 20:
        return None
    l = leader.reindex(common).ffill().bfill()
    b = benchmark.reindex(common).ffill().bfill()
    if b.min() <= 0:
        return None
    return (l / b).dropna()


def _rs_trend(ratio: pd.Series, fast: int = 5, slow: int = 20) -> str:
    """Rising / Flat / Falling from fast vs slow MA on ratio."""
    if ratio is None or len(ratio) < slow:
        return "Flat"
    r = ratio.iloc[-slow:]
    ma_fast = r.iloc[-fast:].mean() if len(r) >= fast else r.iloc[-1]
    ma_slow = r.mean()
    if ma_slow == 0:
        return "Flat"
    pct = (ma_fast - ma_slow) / ma_slow
    if pct > 0.005:
        return "Rising"
    if pct < -0.005:
        return "Falling"
    return "Flat"


def compute_rs_and_trend(
    period: str = "6mo",
) -> dict:
    """
    Fetch SPY, QQQ, XLK, XLF, XLE, XLI, optional RSP.
    Compute RS ratio and short-term trend for XLK/SPY, QQQ/SPY, RSP/SPY.
    Returns dict with rs_xlk_spy, rs_qqq_spy, rs_rsp_spy (ratio series), trends, and participation.
    """
    spy = fetch_ohlcv_safe("SPY", period)
    qqq = fetch_ohlcv_safe("QQQ", period)
    xlk = fetch_ohlcv_safe("XLK", period)
    xlf = fetch_ohlcv_safe("XLF", period)
    xle = fetch_ohlcv_safe("XLE", period)
    xli = fetch_ohlcv_safe("XLI", period)
    rsp = fetch_ohlcv_safe("RSP", period)

    out = {
        "rs_xlk_spy": None,
        "rs_qqq_spy": None,
        "rs_rsp_spy": None,
        "trend_xlk": "Flat",
        "trend_qqq": "Flat",
        "trend_rsp": "Flat",
        "participation_narrow": None,  # True when SPY strong but RSP lagging
    }

    rs_xlk = _rs_ratio(xlk, spy) if xlk is not None and spy is not None else None
    rs_qqq = _rs_ratio(qqq, spy) if qqq is not None and spy is not None else None
    rs_rsp = _rs_ratio(rsp, spy) if rsp is not None and spy is not None else None

    out["rs_xlk_spy"] = float(rs_xlk.iloc[-1]) if rs_xlk is not None and len(rs_xlk) else None
    out["rs_qqq_spy"] = float(rs_qqq.iloc[-1]) if rs_qqq is not None and len(rs_qqq) else None
    out["rs_rsp_spy"] = float(rs_rsp.iloc[-1]) if rs_rsp is not None and len(rs_rsp) else None

    out["trend_xlk"] = _rs_trend(rs_xlk) if rs_xlk is not None else "Flat"
    out["trend_qqq"] = _rs_trend(rs_qqq) if rs_qqq is not None else "Flat"
    out["trend_rsp"] = _rs_trend(rs_rsp) if rs_rsp is not None else "Flat"

    # Participation: narrow when SPY near highs but RSP/SPY ratio declining (equal-weight lagging)
    if rs_rsp is not None and spy is not None and len(rs_rsp) >= 20:
        spy_20d = float(spy.iloc[-1] / spy.iloc[-20]) if len(spy) >= 20 else 1.0
        rsp_trend = out["trend_rsp"]
        if spy_20d > 1.02 and rsp_trend == "Falling":
            out["participation_narrow"] = True
        elif rsp_trend == "Rising":
            out["participation_narrow"] = False
        else:
            out["participation_narrow"] = False

    return out


def get_tech_leadership(rs_data: dict) -> str:
    """Tech leadership: Rising / Flat / Falling from XLK and QQQ RS trend."""
    t_xlk = rs_data.get("trend_xlk") or "Flat"
    t_qqq = rs_data.get("trend_qqq") or "Flat"
    if t_xlk == "Falling" or t_qqq == "Falling":
        return "Falling"
    if t_xlk == "Rising" and t_qqq == "Rising":
        return "Rising"
    return "Flat"


def get_market_breadth_label(rs_data: dict) -> str:
    """Market breadth: Strong / Neutral / Weak. Uses RSP/SPY participation proxy."""
    narrow = rs_data.get("participation_narrow")
    trend_rsp = rs_data.get("trend_rsp") or "Flat"
    if narrow is True:
        return "Weak"
    if trend_rsp == "Rising":
        return "Strong"
    return "Neutral"


def get_rotation_risk(
    rs_data: dict,
    vix: float | None = None,
    real_yield: float | None = None,
) -> str:
    """
    Rotation risk: Low / Medium / High.
    High when: tech RS falling and (VIX elevated or real yield high or breadth weak).
    """
    tech = get_tech_leadership(rs_data)
    breadth = get_market_breadth_label(rs_data)

    if tech == "Falling":
        if breadth == "Weak" or (vix is not None and vix > 20) or (real_yield is not None and real_yield > 2.0):
            return "High"
        if vix is not None and vix > 16:
            return "Medium"
        return "Medium"
    if tech == "Flat" and breadth == "Weak":
        return "Medium"
    if tech == "Rising" and breadth == "Strong":
        return "Low"
    return "Medium"


def get_market_regime(
    period: str = "6mo",
    vix: float | None = None,
    real_yield: float | None = None,
) -> dict:
    """
    Single call for dashboard: breadth, tech leadership, rotation risk.
    Returns:
      market_breadth: Strong | Neutral | Weak
      tech_leadership: Rising | Flat | Falling
      rotation_risk: Low | Medium | High
      participation_narrow: bool | None
      rs_xlk_spy, rs_qqq_spy, rs_rsp_spy: last ratio values
    """
    rs_data = compute_rs_and_trend(period=period)
    return {
        "market_breadth": get_market_breadth_label(rs_data),
        "tech_leadership": get_tech_leadership(rs_data),
        "rotation_risk": get_rotation_risk(rs_data, vix=vix, real_yield=real_yield),
        "participation_narrow": rs_data.get("participation_narrow"),
        "rs_xlk_spy": rs_data.get("rs_xlk_spy"),
        "rs_qqq_spy": rs_data.get("rs_qqq_spy"),
        "rs_rsp_spy": rs_data.get("rs_rsp_spy"),
    }


# Step-down map: when rotation risk is High, tech tickers get one notch more conservative
# short_suggestion / medium_suggestion values: "HOLD/ADD", "HOLD", "CONSIDER TRIM"
_SUGGESTION_STEP_DOWN = [
    ("HOLD/ADD", "HOLD"),
    ("ADD", "HOLD"),
    ("BUY", "HOLD"),
    ("HOLD", "CONSIDER TRIM"),
    ("CONSIDER TRIM", "CONSIDER TRIM"),
    ("TRIM", "TRIM"),
]


def _is_tech_sector(sector: str | None) -> bool:
    if not sector:
        return False
    s = (sector or "").lower()
    return "tech" in s or "technology" in s or "communication" in s


def apply_rotation_step_down(
    results: list[dict],
    market_regime: dict,
    get_sector_fn=None,
) -> list[dict]:
    """
    When rotation_risk is High, step down short_suggestion and medium_suggestion
    for tech-sector tickers (ADD→HOLD, HOLD→CONSIDER TRIM).
    get_sector_fn(ticker) -> sector string; if None, uses signals.providers.get_sector_and_industry.
    Modifies results in place and returns results.
    """
    if market_regime.get("rotation_risk") != "High":
        return results

    if get_sector_fn is None:
        try:
            from .providers import get_sector_and_industry
            def _sector(ticker):
                info = get_sector_and_industry(ticker) or {}
                return info.get("sector") or ""
            get_sector_fn = _sector
        except Exception:
            get_sector_fn = lambda ticker: ""

    for r in results:
        if r.get("error"):
            continue
        ticker = r.get("ticker")
        if not ticker:
            continue
        sector = get_sector_fn(ticker)
        if not _is_tech_sector(sector):
            continue
        short = (r.get("short_suggestion") or "").strip().upper()
        med = (r.get("medium_suggestion") or "").strip().upper()
        new_short = None
        new_med = None
        for k, v in _SUGGESTION_STEP_DOWN:
            if k in short or short == k:
                new_short = v
                break
        for k, v in _SUGGESTION_STEP_DOWN:
            if k in med or med == k:
                new_med = v
                break
        if new_short and new_short != short:
            r["short_suggestion"] = new_short
            r["rotation_stepped_down"] = True
        if new_med and new_med != med:
            r["medium_suggestion"] = new_med
            r["rotation_stepped_down"] = True

    return results
