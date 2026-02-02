"""
Portfolio "doctor": per-holding suggestions, regime counts, concentration, cash deployment,
sector allocation, YTD/1Y return, pairwise correlation.
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
        cost_basis = h.get("cost_basis") if isinstance(h, dict) else None
        account = h.get("account") if isinstance(h, dict) else None
        r = results_by_ticker.get(ticker)
        if not r or r.get("close") is None:
            entry = {"ticker": ticker, "quantity": qty, "price": None, "value": None, "pct": None, "score": None, "regime": None, "suggestion": "N/A"}
            if account:
                entry["account"] = account
            per_holding.append(entry)
            continue
        price = float(r["close"])
        value = qty * price
        total_value += value
        score = r.get("composite_buy")
        regime = r.get("regime", "")
        suggestion = _suggestion(score, buy_min, sell_max)
        entry = {"ticker": ticker, "quantity": qty, "price": price, "value": value, "pct": None, "score": score, "regime": regime, "suggestion": suggestion}
        if account:
            entry["account"] = account
        if cost_basis is not None:
            try:
                cost = float(cost_basis)
                entry["cost_basis"] = cost
                entry["cost_value"] = qty * cost
                entry["gain_loss"] = round(value - (qty * cost), 2)
                entry["gain_loss_pct"] = round(100 * (value - (qty * cost)) / (qty * cost), 1) if cost > 0 else None
            except (TypeError, ValueError):
                pass
        per_holding.append(entry)

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

    # Largest position (include score/regime)
    largest = None
    if per_holding:
        with_value = [h for h in per_holding if h["pct"] is not None]
        if with_value:
            largest_h = max(with_value, key=lambda x: x["pct"])
            largest = {
                "ticker": largest_h["ticker"],
                "pct": largest_h["pct"],
                "value": largest_h["value"],
                "score": largest_h.get("score"),
                "regime": largest_h.get("regime"),
            }

    # Top 3 combined %
    sorted_by_pct = sorted([h for h in per_holding if h.get("pct") is not None], key=lambda x: -(x["pct"] or 0))[:3]
    top3_pct = round(sum(h["pct"] for h in sorted_by_pct), 1) if sorted_by_pct else 0

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

    # Sector allocation (aggregate by sector)
    sector_allocation = {}
    try:
        from signals.providers import get_sector_and_industry
        for h in per_holding:
            if h.get("value") is None or h.get("pct") is None:
                continue
            t = h.get("ticker")
            info = get_sector_and_industry(t) or {}
            sector = (info.get("sector") or "Unknown").strip() or "Unknown"
            sector_allocation[sector] = sector_allocation.get(sector, 0) + (h["pct"] or 0)
        sector_allocation = [{"sector": s, "pct": round(p, 1)} for s, p in sorted(sector_allocation.items(), key=lambda x: -x[1])]
    except Exception:
        sector_allocation = []

    # Pairwise correlation (simplified: flag if any pair > 0.8)
    correlation_alerts = []
    try:
        from signals.fetcher import fetch_ohlcv_safe
        tickers_with_value = [h["ticker"] for h in per_holding if h.get("value") and h.get("pct")]
        if len(tickers_with_value) >= 2:
            returns_dict = {}
            for t in tickers_with_value[:8]:  # limit to 8 to avoid slowdown
                close = fetch_ohlcv_safe(t, "1y")
                if close is not None and len(close) >= 60:
                    ret = close.pct_change().dropna()
                    returns_dict[t] = ret
            if returns_dict:
                import pandas as pd
                df = pd.DataFrame(returns_dict).dropna(how="all")
                if len(df) >= 20:
                    corr = df.corr()
                    for i, t1 in enumerate(corr.columns):
                        for t2 in corr.columns[i + 1:]:
                            c = corr.loc[t1, t2]
                            if pd.notna(c) and c > 0.8:
                                correlation_alerts.append(f"{t1}-{t2}: {c:.2f}")
    except Exception:
        pass

    return {
        "per_holding": per_holding,
        "total_value": total_value,
        "avg_score": round(avg_score, 1),
        "regime_counts": regime_counts,
        "largest_position": largest,
        "top3_pct": top3_pct,
        "concentration_alert": concentration_alert,
        "cash_deployment": cash_deployment[:10],  # top 10
        "sector_allocation": sector_allocation,
        "correlation_alerts": correlation_alerts[:5],  # top 5 pairs
    }
