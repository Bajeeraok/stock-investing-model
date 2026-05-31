"""
One-line external screener context from OHLCV fields already on ticker detail (no extra API).
Mirrors how retail tools split MA trend vs RSI timing.
"""
from __future__ import annotations

from typing import Any


def _safe_float(v: Any) -> float | None:
    try:
        if v is None:
            return None
        f = float(v)
        return f if f == f else None
    except (TypeError, ValueError):
        return None


def _rsi_zone(rsi: float | None) -> str:
    if rsi is None:
        return "unknown"
    if rsi >= 70:
        return "overbought"
    if rsi <= 35:
        return "oversold"
    if rsi >= 55:
        return "firm"
    if rsi <= 45:
        return "soft"
    return "neutral"


def _ma_alignment(price: float | None, ma20: float | None, ma50: float | None, ma200: float | None) -> tuple[str, int, int]:
    mas = [m for m in (ma20, ma50, ma200) if m is not None and m > 0]
    if price is None or price <= 0 or not mas:
        return "unknown", 0, len(mas)
    above = sum(1 for m in mas if price > m)
    total = len(mas)
    if above == total and total >= 2:
        return "bullish", above, total
    if above == 0:
        return "bearish", above, total
    return "mixed", above, total


def build_external_context_chip(
    *,
    rsi: float | None = None,
    current_price: float | None = None,
    ma20: float | None = None,
    ma50: float | None = None,
    ma200: float | None = None,
    macd_hist: float | None = None,
    regime: str | None = None,
) -> dict[str, Any]:
    rsi_f = _safe_float(rsi)
    price = _safe_float(current_price)
    m20 = _safe_float(ma20)
    m50 = _safe_float(ma50)
    m200 = _safe_float(ma200)
    macd = _safe_float(macd_hist)
    rz = _rsi_zone(rsi_f)
    ma_align, ma_above, ma_total = _ma_alignment(price, m20, m50, m200)

    tags: list[str] = []
    if ma_align == "bullish":
        tags.append(f"MAs: bullish ({ma_above}/{ma_total} above)")
    elif ma_align == "bearish":
        tags.append(f"MAs: bearish (below {ma_total} MAs)")
    elif ma_align == "mixed":
        tags.append(f"MAs: mixed ({ma_above}/{ma_total} above)")
    if rz == "overbought" and rsi_f is not None:
        tags.append(f"RSI: extended ({rsi_f:.0f})")
    elif rz == "oversold" and rsi_f is not None:
        tags.append(f"RSI: oversold ({rsi_f:.0f})")
    elif rsi_f is not None:
        tags.append(f"RSI: {rsi_f:.0f}")

    if macd is not None:
        tags.append(f"MACD hist: {'+' if macd >= 0 else ''}{macd:.2f}")

    reg = str(regime or "").upper().strip()
    if reg:
        tags.append(f"Regime: {reg}")

    # How popular screeners would roughly read the same tape
    if ma_align == "bullish" and rz == "overbought":
        screener = "mixed"
        summary = (
            "External screeners often show Strong Buy on moving averages while flagging RSI as overbought — "
            "trend is up; chasing the close is the usual disagreement point."
        )
    elif ma_align == "bullish" and rz in ("neutral", "firm", "soft"):
        screener = "agree_trend"
        summary = (
            "External trend screens (MA stack) likely read bullish; RSI is not extreme — "
            "closer to a trend-follow setup than a blow-off top."
        )
    elif ma_align == "bullish" and rz == "oversold":
        screener = "agree_dip"
        summary = (
            "Trend screens bullish with RSI oversold — aligns with buy-the-dip tools "
            "(pullback in an uptrend)."
        )
    elif ma_align == "bearish":
        screener = "caution"
        summary = (
            "Price below key moving averages — most trend screeners lean cautious or sell "
            "despite any single-indicator bounce."
        )
    else:
        screener = "mixed"
        summary = (
            "Mixed MA/RSI read — compare to your broker screener; use One Answer for execution timing."
        )

    return {
        "rsi": round(rsi_f, 1) if rsi_f is not None else None,
        "rsi_zone": rz,
        "ma_alignment": ma_align,
        "ma_above_count": ma_above,
        "ma_total": ma_total,
        "macd_hist": round(macd, 3) if macd is not None else None,
        "regime": reg or None,
        "tags": tags[:5],
        "screener_alignment": screener,
        "summary_line": summary,
        "source_note": "Derived from our EOD bar (same inputs as RSI/MA/MACD on this page) — not a live third-party feed.",
    }


def build_external_context_from_response(response: dict[str, Any]) -> dict[str, Any]:
    """Convenience wrapper for ticker detail response dict."""
    return build_external_context_chip(
        rsi=_safe_float(response.get("rsi")),
        current_price=_safe_float(response.get("current_price") or response.get("close")),
        ma20=_safe_float(response.get("ma20")),
        ma50=_safe_float(response.get("ma50")),
        ma200=_safe_float(response.get("ma200")),
        macd_hist=_safe_float(response.get("macd_hist")),
        regime=response.get("regime") or response.get("global_market_regime"),
    )
