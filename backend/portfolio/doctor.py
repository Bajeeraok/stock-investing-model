"""
Portfolio "doctor": per-holding suggestions, regime counts, concentration, cash deployment,
sector allocation, YTD/1Y return, pairwise correlation.
"""
from __future__ import annotations

from signals.score_interpretation import effective_buy_min


def _suggestion(
    score: float | None,
    buy_min: float = 65,
    sell_max: float = 35,
    interpretation_style: str = "TRENDING",
) -> str:
    if score is None:
        return "N/A"
    s = float(score)
    if interpretation_style == "MEAN_REVERTING":
        s = 100.0 - s
    if s >= buy_min:
        return "HOLD/ADD"
    if s <= sell_max:
        return "CONSIDER TRIM"
    return "HOLD"


def _suggestion_from_confidence(
    confidence: float | None,
    action: str | None,
    add_min_confidence_pct: float = 70.0,
    trim_max_confidence_pct: float = 30.0,
) -> str:
    """Map 7-layer confidence action to portfolio suggestion. Thresholds align with config model_rules (add_min_confidence, trim_max_confidence)."""
    if confidence is None and not action:
        return "N/A"
    if action:
        if action in ("STRONG BUY", "BUY"):
            return "HOLD/ADD"
        if action in ("REDUCE", "AVOID"):
            return "CONSIDER TRIM"
    if confidence is not None:
        add_thresh = add_min_confidence_pct / 100.0
        trim_thresh = trim_max_confidence_pct / 100.0
        if confidence >= add_thresh:
            return "HOLD/ADD"
        if confidence < trim_thresh:
            return "CONSIDER TRIM"
    return "HOLD"


def _action_today_line(
    score: float | None,
    confidence_pct: float | None,
    regime: str | None,
    suggestion: str,
    earnings_note: str | None,
) -> str:
    """Single-line retail cue: confidence or score, regime, suggestion, earnings if soon."""
    parts: list[str] = []
    if confidence_pct is not None:
        parts.append(f"{confidence_pct:.0f}% conf")
    elif score is not None:
        parts.append(f"score {score:.0f}")
    if regime:
        parts.append(str(regime))
    if suggestion and suggestion != "N/A":
        parts.append(suggestion.replace("/", " ").strip())
    if earnings_note and "Earnings" in earnings_note:
        parts.append(earnings_note.strip())
    return " · ".join(parts) if parts else "Review levels"


def portfolio_report(
    holdings: list[dict],
    results: list[dict],
    watchlist: list[str],
    score_cfg: dict | None = None,
    concentration_threshold_pct: float = 20.0,
    cash_deploy_min_score: float = 70.0,
    confidence_by_ticker: dict | None = None,
    model_rules: dict | None = None,
) -> dict:
    """
    Build full portfolio report.

    holdings: [{ticker, quantity, cost_basis?}, ...]
    results: from run_signals, [{ticker, close, composite_buy, regime, ...}, ...]
    watchlist: all tickers we have signals for
    score_cfg: {buy_min, sell_max, optional buy_min_by_ticker} for suggestions
    concentration_threshold_pct: alert if any position > this % of portfolio
    cash_deploy_min_score: min score for "deploy cash" suggestions
    confidence_by_ticker: optional {ticker: {confidence, action, breakdown, ...}} from run_confidence (7-layer)

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
    sell_max = score_cfg.get("sell_max", 35)
    model_rules = model_rules or {}
    add_min_conf_pct = float(model_rules.get("add_min_confidence", 70))
    trim_max_conf_pct = float(model_rules.get("trim_max_confidence", 30))

    results_by_ticker = {r["ticker"]: r for r in results if not r.get("error")}

    per_holding = []
    total_value = 0.0

    for h in holdings:
        ticker = h.get("ticker") if isinstance(h, dict) else h
        qty = h.get("quantity", 1) if isinstance(h, dict) else 1
        cost_basis = h.get("cost_basis") if isinstance(h, dict) else None
        account = h.get("account") if isinstance(h, dict) else None
        purchase_date = (h.get("purchase_date") or h.get("acquisition_date")) if isinstance(h, dict) else None
        r = results_by_ticker.get(ticker)
        if not r or r.get("close") is None:
            entry = {
                "ticker": ticker,
                "quantity": qty,
                "price": None,
                "value": None,
                "pct": None,
                "score": None,
                "regime": None,
                "suggestion": "N/A",
                "action_today": "No snapshot — refresh signals",
            }
            if account:
                entry["account"] = account
            per_holding.append(entry)
            continue
        price = float(r["close"])
        value = qty * price
        total_value += value
        score = r.get("composite_buy")
        regime = r.get("regime", "")
        conf_data = (confidence_by_ticker or {}).get(ticker)
        earn_note = r.get("earnings_note")
        if conf_data is not None and conf_data.get("confidence") is not None:
            suggestion = _suggestion_from_confidence(conf_data.get("confidence"), conf_data.get("action"), add_min_conf_pct, trim_max_conf_pct)
            conf_pct = round(conf_data["confidence"] * 100, 1)
            entry = {
                "ticker": ticker,
                "quantity": qty,
                "price": price,
                "value": value,
                "pct": None,
                "score": score,
                "regime": regime,
                "suggestion": suggestion,
                "confidence": conf_pct,
                "action": conf_data.get("action"),
                "score_interpretation_style": r.get("score_interpretation_style") or "TRENDING",
                "action_today": _action_today_line(score, conf_pct, regime, suggestion, earn_note),
            }
        else:
            interp = r.get("score_interpretation_style") or "TRENDING"
            buy_min_row = effective_buy_min(ticker, score_cfg)
            suggestion = _suggestion(score, buy_min_row, sell_max, interpretation_style=interp)
            entry = {
                "ticker": ticker,
                "quantity": qty,
                "price": price,
                "value": value,
                "pct": None,
                "score": score,
                "regime": regime,
                "suggestion": suggestion,
                "buy_min": buy_min_row,
                "score_interpretation_style": interp,
                "action_today": _action_today_line(score, None, regime, suggestion, earn_note),
            }
        if earn_note:
            entry["earnings_note"] = earn_note
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
        if purchase_date is not None:
            entry["purchase_date"] = purchase_date
        per_holding.append(entry)

    # Fill pct
    for h in per_holding:
        if h["value"] is not None and total_value > 0:
            h["pct"] = round(100 * h["value"] / total_value, 1)

    # Regime counts
    regime_counts = {"UP": 0, "NEUTRAL": 0, "DOWN": 0}
    scores_for_avg = []
    confidences_for_avg = []
    score_confidence_mismatch_count = 0
    for h in per_holding:
        if h["regime"]:
            regime_counts[h["regime"]] = regime_counts.get(h["regime"], 0) + 1
        if h["score"] is not None:
            scores_for_avg.append(h["score"])
        if h.get("confidence") is not None:
            confidences_for_avg.append(float(h["confidence"]))
        sc = h.get("score")
        cf = h.get("confidence")
        if sc is not None and cf is not None:
            if (float(sc) >= 65 and float(cf) < 55) or (float(sc) <= 35 and float(cf) >= 55):
                score_confidence_mismatch_count += 1
    avg_score = sum(scores_for_avg) / len(scores_for_avg) if scores_for_avg else 0.0
    avg_confidence = (
        round(sum(confidences_for_avg) / len(confidences_for_avg), 1) if confidences_for_avg else None
    )

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
                "confidence": largest_h.get("confidence"),
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

    # Cash deployment: watchlist tickers NOT in portfolio with score/confidence >= threshold
    portfolio_tickers = {h.get("ticker") if isinstance(h, dict) else h for h in holdings}
    cash_deployment = []
    for r in results:
        if r.get("error"):
            continue
        t = r["ticker"]
        if t in portfolio_tickers:
            continue
        score = r.get("composite_buy")
        conf_data = (confidence_by_ticker or {}).get(t)
        use_confidence = conf_data is not None and conf_data.get("confidence") is not None
        if use_confidence:
            conf_val = conf_data["confidence"]
            if conf_val >= (add_min_conf_pct / 100.0):
                cash_deployment.append({"ticker": t, "score": score, "regime": r.get("regime", ""), "confidence": round(conf_val * 100, 1), "action": conf_data.get("action")})
        elif score is not None:
            interp = r.get("score_interpretation_style") or "TRENDING"
            eff = 100.0 - float(score) if interp == "MEAN_REVERTING" else float(score)
            deploy_bar = effective_buy_min(t, score_cfg)
            if eff >= deploy_bar:
                cash_deployment.append({
                    "ticker": t,
                    "score": score,
                    "regime": r.get("regime", ""),
                    "score_interpretation_style": interp,
                    "buy_min": deploy_bar,
                })
    cash_deployment.sort(key=lambda x: -(x.get("confidence") if x.get("confidence") is not None else (x.get("score") or 0)))

    # Theme concentration: mega-cap (AAPL, MSFT, GOOGL, AMZN, NVDA, META, TSLA) combined %
    MEGA_CAP = {"AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA"}
    mega_cap_pct = 0.0
    for h in per_holding:
        if h.get("ticker") in MEGA_CAP and h.get("pct") is not None:
            mega_cap_pct += h["pct"]
    mega_cap_pct = round(mega_cap_pct, 1)

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
        "avg_confidence": avg_confidence,
        "score_confidence_mismatch_count": score_confidence_mismatch_count,
        "regime_counts": regime_counts,
        "largest_position": largest,
        "top3_pct": top3_pct,
        "concentration_alert": concentration_alert,
        "cash_deployment": cash_deployment[:10],  # top 10
        "sector_allocation": sector_allocation,
        "correlation_alerts": correlation_alerts[:5],  # top 5 pairs
        "mega_cap_pct": mega_cap_pct,
    }


def allocation_recommendations(
    report: dict,
    results: list[dict],
    opportunities: list[dict],
    doctor_cfg: dict | None = None,
    confidence_by_ticker: dict | None = None,
) -> dict:
    """
    Portfolio Doctor: trim/add recommendations with $ and % amounts and suggested prices.
    Uses risk_appetite, goal, and optional target $ over time to tune aggressiveness.
    Add candidates come from opportunities (deduped by ticker).
    When confidence_by_ticker is provided (7-layer run_confidence), uses calibrated
    confidence for trim/add thresholds and ranking instead of technical score.
    """
    doctor_cfg = doctor_cfg or {}
    model_rules = doctor_cfg.get("model_rules") or {}
    risk_appetite = (doctor_cfg.get("risk_appetite") or "moderate").lower()
    goal = (doctor_cfg.get("goal") or "medium").lower()
    target_value = doctor_cfg.get("target_portfolio_value")
    time_years = doctor_cfg.get("time_period_years", 10)
    if target_value is not None:
        try:
            target_value = float(target_value)
        except (TypeError, ValueError):
            target_value = None
    try:
        time_years = int(time_years)
    except (TypeError, ValueError):
        time_years = 10

    total_value = report.get("total_value") or 0.0
    per_holding = report.get("per_holding") or []
    results_by_ticker = {r["ticker"]: r for r in results if not r.get("error")}

    # Implied CAGR from target $ and time
    implied_cagr_pct = None
    if target_value is not None and total_value > 0 and time_years > 0:
        try:
            import math
            ratio = target_value / total_value
            if ratio > 0:
                implied_cagr_pct = round((ratio ** (1.0 / time_years) - 1) * 100, 1)
        except Exception:
            pass

    # Profile: how aggressive (trim/add thresholds, position caps)
    # Score scale (0-100) when confidence not available; confidence scale (0-1) when available
    trim_score_threshold = {"conservative": 45, "moderate": 40, "aggressive": 35}.get(risk_appetite, 40)
    trim_conf_threshold = {"conservative": 0.45, "moderate": 0.45, "aggressive": 0.40}.get(risk_appetite, 0.45)
    max_position_pct = {"conservative": 15, "moderate": 20, "aggressive": 25}.get(risk_appetite, 20)
    add_min_score = {"conservative": 72, "moderate": 70, "aggressive": 65}.get(risk_appetite, 70)
    add_min_conf = {"conservative": 0.72, "moderate": 0.65, "aggressive": 0.58}.get(risk_appetite, 0.65)
    use_model_rules = bool(model_rules.get("add_min_confidence") is not None or model_rules.get("trim_max_confidence") is not None)
    cash_deploy_min = float(doctor_cfg.get("cash_deploy_min_score") or 70)
    if use_model_rules:
        if model_rules.get("add_min_confidence") is not None:
            add_min_conf = float(model_rules["add_min_confidence"]) / 100.0
        if model_rules.get("trim_max_confidence") is not None:
            trim_conf_threshold = float(model_rules["trim_max_confidence"]) / 100.0
        add_min_score = int(cash_deploy_min)
    # If implied CAGR is high, nudge toward more aggressive (trim weak positions to redeploy)
    if not use_model_rules:
        if implied_cagr_pct is not None and implied_cagr_pct > 10:
            trim_score_threshold = min(trim_score_threshold + 5, 50)
            trim_conf_threshold = min(trim_conf_threshold + 0.05, 0.50)
        elif implied_cagr_pct is not None and implied_cagr_pct < 4:
            trim_score_threshold = max(trim_score_threshold - 3, 35)
            trim_conf_threshold = max(trim_conf_threshold - 0.05, 0.35)
    else:
        if implied_cagr_pct is not None and implied_cagr_pct > 10:
            trim_score_threshold = min(trim_score_threshold + 5, 50)
        elif implied_cagr_pct is not None and implied_cagr_pct < 4:
            trim_score_threshold = max(trim_score_threshold - 3, 35)

    # ---- TRIM ----
    conf_map = confidence_by_ticker or {}
    trim_list = []
    for h in per_holding:
        if h.get("value") is None or h.get("value") <= 0 or total_value <= 0:
            continue
        ticker = h["ticker"]
        score = h.get("score")
        conf_data = conf_map.get(ticker)
        conf_val = conf_data.get("confidence") if conf_data and isinstance(conf_data, dict) else None
        use_conf = conf_val is not None
        if use_conf:
            if conf_val > trim_conf_threshold:
                continue
        else:
            if score is None or score > trim_score_threshold:
                continue
        current_value = float(h["value"])
        current_pct = (h.get("pct") or 0) or round(100 * current_value / total_value, 1)
        r = results_by_ticker.get(ticker)
        sell_price = None
        if r:
            sell_price = r.get("suggested_sell_price")
            if sell_price is None and isinstance(r.get("st_band"), dict) and r["st_band"].get("high") is not None:
                sell_price = r["st_band"]["high"]
            if sell_price is not None:
                sell_price = round(float(sell_price), 2)
            if sell_price is None and r.get("close") is not None:
                sell_price = round(float(r["close"]), 2)
        if sell_price is None:
            sell_price = h.get("price")
        if sell_price is not None:
            sell_price = round(float(sell_price), 2)

        # Suggest trim: bring position to max_position_pct or trim 25/50/75% of excess (conservative = trim more)
        target_pct = min(current_pct, max_position_pct)
        trim_pct_of_position = 25
        if current_pct > max_position_pct:
            excess_pct = current_pct - max_position_pct
            trim_pct_of_position = min(75, max(25, round(excess_pct / current_pct * 100, 0)))
        suggest_trim_pct = round(current_pct * (trim_pct_of_position / 100), 1)
        suggest_trim_dollars = round(current_value * (trim_pct_of_position / 100), 2)
        if use_conf:
            reason = f"7-layer confidence {conf_val*100:.0f}% ({conf_data.get('action') or 'N/A'}), regime {h.get('regime') or 'N/A'}"
        else:
            reason = f"Score {score:.0f}, regime {h.get('regime') or 'N/A'}"
        if current_pct > max_position_pct:
            reason += f"; position {current_pct}% > max {max_position_pct}%"

        trim_list.append({
            "ticker": ticker,
            "current_pct": current_pct,
            "current_value": round(current_value, 2),
            "max_position_pct": max_position_pct,
            "suggest_trim_pct": suggest_trim_pct,
            "suggest_trim_dollars": suggest_trim_dollars,
            "sell_price": sell_price,
            "reason": reason.strip(),
            "score": score,
            "regime": h.get("regime"),
            "confidence": round(conf_val * 100, 1) if conf_val is not None else None,
            "action": conf_data.get("action") if conf_data else None,
        })
    trim_list.sort(key=lambda x: ((x.get("confidence") if x.get("confidence") is not None else x["score"] or 0), -x["current_value"]))

    # ---- ADD: merge opportunities (dedupe by ticker, prefer higher confidence/score) ----
    portfolio_tickers = {h["ticker"] for h in per_holding}
    add_candidates = []
    seen = set()
    for o in opportunities:
        t = o.get("ticker")
        if not t or t in portfolio_tickers or t in seen:
            continue
        score = o.get("composite_buy") or o.get("score")
        conf_data = conf_map.get(t)
        conf_val = conf_data.get("confidence") if conf_data and isinstance(conf_data, dict) else None
        use_conf = conf_val is not None and conf_val >= add_min_conf
        use_score = score is not None and score >= add_min_score
        if not use_conf and not use_score:
            continue
        seen.add(t)
        add_candidates.append({
            "ticker": t,
            "score": float(score) if score is not None else None,
            "regime": o.get("regime") or "",
            "close": o.get("close"),
            "source": "opportunities",
            "confidence": round(conf_val * 100, 1) if conf_val is not None else None,
            "action": conf_data.get("action") if conf_data else None,
        })
    def _add_sort_key(x):
        c = x.get("confidence")
        s = x.get("score") or 0
        return -(c if c is not None else s)
    add_candidates.sort(key=_add_sort_key)

    # Suggest add size: equal-weight slice of "deployable" (trim proceeds or 5% of portfolio)
    trim_proceeds = sum(x["suggest_trim_dollars"] for x in trim_list)
    deployable = trim_proceeds if trim_proceeds > 0 else total_value * 0.05
    add_cap = add_candidates[:12]
    n_add = len(add_cap)
    add_dollars_each = round(deployable / n_add, 2) if n_add else 0

    add_list = []
    for c in add_cap:
        ticker = c["ticker"]
        r = results_by_ticker.get(ticker)
        buy_price = None
        if r:
            buy_price = r.get("suggested_buy_price")
            if buy_price is None and isinstance(r.get("st_band"), dict) and r["st_band"].get("low") is not None:
                buy_price = r["st_band"]["low"]
            if buy_price is not None:
                buy_price = round(float(buy_price), 2)
            if buy_price is None and r.get("close") is not None:
                buy_price = round(float(r["close"]), 2)
        if buy_price is None and c.get("close") is not None:
            try:
                buy_price = round(float(c["close"]), 2)
            except (TypeError, ValueError):
                pass
        suggest_add_dollars = add_dollars_each
        suggest_add_pct = round(100 * suggest_add_dollars / total_value, 1) if total_value > 0 else 0
        entry = {
            "ticker": ticker,
            "score": round(c["score"], 1) if c.get("score") is not None else None,
            "regime": c["regime"],
            "suggest_add_pct": suggest_add_pct,
            "suggest_add_dollars": suggest_add_dollars,
            "buy_price": buy_price,
            "source": c["source"],
        }
        if c.get("confidence") is not None:
            entry["confidence"] = c["confidence"]
        if c.get("action"):
            entry["action"] = c["action"]
        add_list.append(entry)

    return {
        "inputs": {
            "risk_appetite": risk_appetite,
            "goal": goal,
            "target_portfolio_value": target_value,
            "time_period_years": time_years,
            "model_rules_unified": use_model_rules,
            "add_min_confidence_pct": round(add_min_conf * 100, 1),
            "trim_max_confidence_pct": round(trim_conf_threshold * 100, 1),
            "max_position_pct": max_position_pct,
        },
        "implied_cagr_pct": implied_cagr_pct,
        "profile": risk_appetite,
        "trim": trim_list,
        "add": add_list,
    }
