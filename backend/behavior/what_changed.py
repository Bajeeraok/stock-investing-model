"""
"What changed?" - diff vs last run for key indicators.
Outputs human-readable changes: "MA50 crossed below MA20", "RSI 72 (overbought)", etc.
Returns (changes, summary) - summary is one compact line for the alert surface.
"""
from __future__ import annotations


def what_changed(prev: dict | None, curr: dict) -> tuple[list[str], str]:
    """
    Compare prev run to curr for a ticker. Return list of change descriptions.
    prev/curr: {rsi, trend_score, ma20, ma50, macd_hist, composite_buy, regime}
    """
    if not prev:
        return [], ""
    changes = []
    prev_rsi = prev.get("rsi")
    curr_rsi = curr.get("rsi")
    prev_trend = prev.get("trend_score")
    curr_trend = curr.get("trend_score")
    prev_ma20 = prev.get("ma20")
    curr_ma20 = curr.get("ma20")
    prev_ma50 = prev.get("ma50")
    curr_ma50 = curr.get("ma50")
    prev_macd = prev.get("macd_hist")
    curr_macd = curr.get("macd_hist")
    prev_regime = prev.get("regime")
    curr_regime = curr.get("regime")
    prev_score = prev.get("composite_buy")
    curr_score = curr.get("composite_buy")
    prev_short = prev.get("short_suggestion")
    curr_short = curr.get("short_suggestion")
    prev_medium = prev.get("medium_suggestion")
    curr_medium = curr.get("medium_suggestion")
    prev_long = prev.get("long_suggestion")
    curr_long = curr.get("long_suggestion")

    # Suggestion changes (short / medium / long)
    if prev_long is not None and curr_long is not None and prev_long != curr_long:
        changes.append(f"Long-term: {prev_long} → {curr_long}")
    if prev_medium is not None and curr_medium is not None and prev_medium != curr_medium:
        changes.append(f"Medium-term: {prev_medium} → {curr_medium}")
    if prev_short is not None and curr_short is not None and prev_short != curr_short:
        changes.append(f"Short-term: {prev_short} → {curr_short}")

    # MA50 vs MA20 cross
    if prev_ma20 is not None and prev_ma50 is not None and curr_ma20 is not None and curr_ma50 is not None:
        prev_above = prev_ma50 > prev_ma20
        curr_above = curr_ma50 > curr_ma20
        if prev_above and not curr_above:
            changes.append("MA50 crossed below MA20 (short-term weakness)")
        elif not prev_above and curr_above:
            changes.append("MA50 crossed above MA20 (short-term strength)")

    # RSI extremes (only when crossing into a band or large move — avoid duplicate noise)
    if curr_rsi is not None:
        if curr_rsi > 70:
            changes.append(f"RSI {curr_rsi:.0f} (overbought)")
        elif curr_rsi < 30:
            changes.append(f"RSI {curr_rsi:.0f} (oversold)")

    # Score move
    if prev_score is not None and curr_score is not None:
        delta = curr_score - prev_score
        if abs(delta) >= 10:
            direction = "up" if delta > 0 else "down"
            changes.append(f"Score {direction} {abs(delta):.0f} pts ({prev_score:.0f} → {curr_score:.0f})")

    # Regime change
    regime_change = bool(prev_regime and curr_regime and prev_regime != curr_regime)
    if regime_change:
        changes.append(f"Regime {prev_regime} → {curr_regime}")

    # MACD flip
    if prev_macd is not None and curr_macd is not None:
        prev_pos = prev_macd > 0
        curr_pos = curr_macd > 0
        if prev_pos and not curr_pos:
            changes.append("MACD turned negative (momentum weakening)")
        elif not prev_pos and curr_pos:
            changes.append("MACD turned positive (momentum improving)")

    if not changes:
        return [], ""

    # One-line summary: score + regime headline, then top drivers (dedupe-friendly)
    ticker = curr.get("ticker", "")
    prev_score_s = f"{prev_score:.0f}" if prev_score is not None else "?"
    curr_score_s = f"{curr_score:.0f}" if curr_score is not None else "?"
    regime_s = f" ({prev_regime}→{curr_regime})" if regime_change else ""
    headline = f"{ticker}: {prev_score_s} → {curr_score_s}{regime_s}".strip()
    detail = "; ".join(changes[:5])
    summary = f"{headline}: {detail}"

    return changes, summary
