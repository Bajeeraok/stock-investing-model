"""
Portfolio "doctor": per-holding suggestions, regime counts, concentration, cash deployment.
"""
from __future__ import annotations


def _suggestion(score: float | None, buy_min: float = 65, sell_max: float = 35) -> str:
    if score is None:
        return "N/A"
    if score >= buy_min:
        return "HOLD/ADD"
    if score <= sell_max:
        return "CONSIDER TRIM"
    return "HOLD"


def portfolio_report(
    holdings: list[dict],
    results: list[dict],
    watchlist: list[str],
    score_cfg: dict | None = None,
    concentration_threshold_pct: float = 20.0,
    cash_deploy_min_score: float = 70.0,
) -> dict:
    """
    Build full portfolio report.

    holdings: [{ticker, quantity, cost_basis?}, ...]
    results: from run_signals, [{ticker, close, composite_buy, regime, ...}, ...]
    watchlist: all tickers we have signals for
    score_cfg: {buy_min, sell_max} for suggestions
    concentration_threshold_pct: alert if any position > this % of portfolio
    cash_deploy_min_score: min score for "deploy cash" suggestions

    Returns dict with:
      - per_holding: [{ticker, quantity, price, value, pct, score, regime, suggestion}]
      - total_value
      - avg_score
      - regime_counts: {UP, NEUTRAL, DOWN}
      - largest_position: {ticker, pct, value}
      - concentration_alert: list of tickers exceeding threshold
      - cash_deployment: top watchlist names NOT in portfolio with score >= cash_deploy_min_score
    """
    score_cfg = score_cfg or {}
    buy_min = score_cfg.get("buy_min", 65)
    sell_max = score_cfg.get("sell_max", 35)

    results_by_ticker = {r["ticker"]: r for r in results if not r.get("error")}

    per_holding = []
    total_value = 0.0

    for h in holdings:
        ticker = h.get("ticker") if isinstance(h, dict) else h
        qty = h.get("quantity", 1) if isinstance(h, dict) else 1
        r = results_by_ticker.get(ticker)
        if not r or r.get("close") is None:
            per_holding.append({
                "ticker": ticker,
                "quantity": qty,
                "price": None,
                "value": None,
                "pct": None,
                "score": None,
                "regime": None,
                "suggestion": "N/A",
            })
            continue
        price = float(r["close"])
        value = qty * price
        total_value += value
        score = r.get("composite_buy")
        regime = r.get("regime", "")
        suggestion = _suggestion(score, buy_min, sell_max)
        per_holding.append({
            "ticker": ticker,
            "quantity": qty,
            "price": price,
            "value": value,
            "pct": None,  # fill after total_value
            "score": score,
            "regime": regime,
            "suggestion": suggestion,
        })

    # Fill pct
    for h in per_holding:
        if h["value"] is not None and total_value > 0:
            h["pct"] = round(100 * h["value"] / total_value, 1)

    # Regime counts
    regime_counts = {"UP": 0, "NEUTRAL": 0, "DOWN": 0}
    scores_for_avg = []
    for h in per_holding:
        if h["regime"]:
            regime_counts[h["regime"]] = regime_counts.get(h["regime"], 0) + 1
        if h["score"] is not None:
            scores_for_avg.append(h["score"])
    avg_score = sum(scores_for_avg) / len(scores_for_avg) if scores_for_avg else 0.0

    # Largest position
    largest = None
    if per_holding:
        with_value = [h for h in per_holding if h["pct"] is not None]
        if with_value:
            largest_h = max(with_value, key=lambda x: x["pct"])
            largest = {"ticker": largest_h["ticker"], "pct": largest_h["pct"], "value": largest_h["value"]}

    # Concentration alert
    concentration_alert = []
    if total_value > 0 and concentration_threshold_pct:
        for h in per_holding:
            if h["pct"] is not None and h["pct"] > concentration_threshold_pct:
                concentration_alert.append(h["ticker"])

    # Cash deployment: watchlist tickers NOT in portfolio with score >= threshold
    portfolio_tickers = {h.get("ticker") if isinstance(h, dict) else h for h in holdings}
    cash_deployment = []
    for r in results:
        if r.get("error"):
            continue
        t = r["ticker"]
        if t in portfolio_tickers:
            continue
        score = r.get("composite_buy")
        if score is not None and score >= cash_deploy_min_score:
            cash_deployment.append({"ticker": t, "score": score, "regime": r.get("regime", "")})
    cash_deployment.sort(key=lambda x: -x["score"])

    return {
        "per_holding": per_holding,
        "total_value": total_value,
        "avg_score": round(avg_score, 1),
        "regime_counts": regime_counts,
        "largest_position": largest,
        "concentration_alert": concentration_alert,
        "cash_deployment": cash_deployment[:10],  # top 10
    }
