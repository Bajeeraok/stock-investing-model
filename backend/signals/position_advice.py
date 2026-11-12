"""
"Your position" sizing for the ticker page — buy side and sell side, from the user's real
holdings (all accounts summed), risk profile, gate mode and protect mode.

Rules (transparent, no score-based sizing — the 10y tests found no score/timing edge):
  • Position cap: 15/20/25% of the book (conservative/moderate/aggressive), same ladder as
    Portfolio Doctor and Tier-1.
  • Buy side: room = cap − current holding, further capped so a stop-out loses at most
    1/2/3% of the book. full_go → full room in 3 tranches; starter_only → one ~25% starter;
    hard_lock → $0 (no new adds).
  • Sell side (held only): default HOLD. Optional trims are shown with share counts:
    over the cap → trim back to the cap; protect mode on → trim to ~50%; short/medium plan
    stop crossings are handled by the holdings-only stop alerts (horizon stops are re-derived
    from the current band and can sit above price, so they are not shown here as 'hit').
"""
from __future__ import annotations

from typing import Any

MAX_POSITION_PCT = {"conservative": 15.0, "moderate": 20.0, "aggressive": 25.0}
RISK_PER_TRADE_PCT = {"conservative": 1.0, "moderate": 2.0, "aggressive": 3.0}
TRANCHES = (0.40, 0.30, 0.30)
STARTER_FRACTION = 0.25


def _f(x: Any) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if v == v else None


def holding_from_report(report: dict | None, ticker: str) -> dict[str, Any]:
    """Sum every row for ticker (the "All" report lists one row per account)."""
    sym = str(ticker or "").upper()
    qty = 0.0
    value = 0.0
    accounts: list[dict[str, Any]] = []
    for h in (report or {}).get("per_holding") or []:
        if not isinstance(h, dict) or str(h.get("ticker") or "").upper() != sym:
            continue
        q = _f(h.get("quantity")) or 0.0
        v = _f(h.get("value")) or 0.0
        qty += q
        value += v
        accounts.append({"account": h.get("account") or "—", "shares": round(q, 4), "value": round(v, 2)})
    return {"shares": round(qty, 4), "value": round(value, 2), "accounts": accounts}


def _whole(dollars: float, price: float) -> int:
    return max(0, int(dollars // price)) if price > 0 else 0


def build_position_advice(
    *,
    ticker: str,
    price: float | None,
    total_value: float | None,
    holding: dict[str, Any] | None,
    risk_profile: str = "moderate",
    entry_mode: str | None = None,
    protect_mode: dict | None = None,
    horizons: dict | None = None,
    max_sizing_pct: float | None = None,
    full_go_via: str | None = None,
) -> dict[str, Any] | None:
    p = _f(price)
    tv = _f(total_value)
    if not p or p <= 0 or not tv or tv <= 0:
        return None
    profile = risk_profile if risk_profile in MAX_POSITION_PCT else "moderate"
    cap_pct = MAX_POSITION_PCT[profile]
    risk_pct = RISK_PER_TRADE_PCT[profile]
    holding = holding or {"shares": 0.0, "value": 0.0, "accounts": []}
    shares = float(holding.get("shares") or 0.0)
    value = shares * p if shares > 0 else float(holding.get("value") or 0.0)
    held = shares > 0 or value > 0
    weight = 100.0 * value / tv
    cap_dollars = tv * cap_pct / 100.0
    horizons = horizons or {}

    # ── Buy side ────────────────────────────────────────────────────────
    room = max(0.0, cap_dollars - value)
    med = horizons.get("medium") or {}
    stop = _f(med.get("stop_loss")) or _f((horizons.get("short") or {}).get("stop_loss"))
    risk_cap = None
    if stop and 0 < stop < p:
        risk_cap = (tv * risk_pct / 100.0) / (p - stop) * p
    full_add = min(room, risk_cap) if risk_cap is not None else room
    mode = str(entry_mode or "").lower()
    ez = med.get("entry_zone") if isinstance(med.get("entry_zone"), dict) else {}
    band_lo, band_hi = _f(ez.get("low")), _f(ez.get("high"))
    above_band = bool(band_hi and p > band_hi * 1.0005)
    band_txt = f"${band_lo:,.2f}–${band_hi:,.2f}" if band_lo and band_hi else "the entry band"
    size_pct = _f(max_sizing_pct)
    if mode == "full_go":
        allowed = full_add * (min(100.0, size_pct) / 100.0 if size_pct else 1.0)
        if full_go_via == "market_regime_override":
            buy_note = "Only Trend weather is blocked and the wider market is bull, so adds are open."
        else:
            buy_note = "All gates clear."
        if size_pct and size_pct < 100:
            buy_note += f" Size capped at ~{size_pct:.0f}% (fair value is Wall St's, not the model's)."
        buy_note += (
            f" Price is above the Swing band: build in 3 tranches only inside {band_txt}, nothing at today's price."
            if above_band
            else f" Build in 3 tranches inside {band_txt}."
        )
    elif mode == "starter_only":
        allowed = full_add * STARTER_FRACTION
        buy_note = "Starter only: one small tranche now; the rest waits for all gates."
    else:
        allowed = 0.0
        buy_note = "No new adds while gates are locked." if mode == "hard_lock" else "No add signal right now."
    if room <= 0:
        allowed = 0.0
        buy_note = f"Already at or above your {cap_pct:.0f}% cap — no adds."
    add_shares = _whole(allowed, p)
    tranches = []
    if add_shares > 0:
        fracs = TRANCHES if mode == "full_go" else (1.0,)
        left = add_shares
        for i, fr in enumerate(fracs):
            n = left if i == len(fracs) - 1 else round(add_shares * fr)
            n = max(0, min(n, left))
            left -= n
            tranches.append({"tranche": i + 1, "shares": n, "dollars": round(n * p, 2)})
    buy = {
        "allowed": add_shares > 0,
        "at_band_only": add_shares > 0 and mode == "full_go" and above_band,
        "band_low": band_lo,
        "band_high": band_hi,
        "shares": add_shares,
        "dollars": round(add_shares * p, 2),
        "new_weight_pct": round(100.0 * (value + add_shares * p) / (tv + 0.0), 2),
        "room_to_cap_dollars": round(room, 2),
        "risk_cap_dollars": round(risk_cap, 2) if risk_cap is not None else None,
        "stop_used": stop,
        "tranches": tranches,
        "note": buy_note,
    }

    # ── Sell side ───────────────────────────────────────────────────────
    sell_options: list[dict[str, Any]] = []
    if held and shares > 0:
        if value > cap_dollars:
            n = min(int(shares), _whole(value - cap_dollars, p) + 1)
            sell_options.append({
                "reason": "over_cap",
                "label": f"Over your {cap_pct:.0f}% cap",
                "shares": n,
                "dollars": round(n * p, 2),
                "note": f"Trim back to {cap_pct:.0f}% of the book to limit single-stock risk.",
            })
        pm = protect_mode or {}
        if pm.get("active"):
            keep = float(pm.get("suggested_position_pct") or 50) / 100.0
            n = int(shares * (1.0 - keep))
            if n > 0:
                sell_options.append({
                    "reason": "protect_mode",
                    "label": f"Protect mode (~{keep * 100:.0f}% position)",
                    "shares": n,
                    "dollars": round(n * p, 2),
                    "note": "Optional insurance: smaller drawdowns, but lower return in our 10-year test.",
                })
    sell = {
        "default": "HOLD" if held else None,
        "options": sell_options,
        "note": (
            "Default is HOLD — the model never sells on a low score alone."
            if held
            else "Not held — nothing to sell."
        ),
    }

    return {
        "ticker": str(ticker).upper(),
        "price": round(p, 4),
        "portfolio_value": round(tv, 2),
        "risk_profile": profile,
        "cap_pct": cap_pct,
        "risk_per_trade_pct": risk_pct,
        "entry_mode": mode or None,
        "held": held,
        "shares": round(shares, 4),
        "value": round(value, 2),
        "weight_pct": round(weight, 2),
        "accounts": holding.get("accounts") or [],
        "buy": buy,
        "sell": sell,
        "scope": "All accounts in the selected portfolio file",
    }


def position_advice_from_cache(
    ticker: str,
    price: float | None,
    *,
    config: dict | None = None,
    entry_mode: str | None = None,
    protect_mode: dict | None = None,
    horizons: dict | None = None,
    max_sizing_pct: float | None = None,
    full_go_via: str | None = None,
) -> dict[str, Any] | None:
    try:
        from config_loader import get_risk_profile
        from signals.cache import get_cached_dashboard, get_last_dashboard_snapshot
    except Exception:
        return None
    report = None
    for payload in (get_cached_dashboard(), get_last_dashboard_snapshot()):
        ps = payload.get("portfolios") if isinstance(payload, dict) else None
        if isinstance(ps, dict) and ps:
            cand = ps.get("All") or next(iter(ps.values()), None)
            if isinstance(cand, dict) and (_f(cand.get("total_value")) or 0) > 0:
                report = cand
                break
    if report is None:
        return None
    return build_position_advice(
        ticker=ticker,
        price=price,
        total_value=report.get("total_value"),
        holding=holding_from_report(report, ticker),
        risk_profile=get_risk_profile(config),
        entry_mode=entry_mode,
        protect_mode=protect_mode,
        horizons=horizons,
        max_sizing_pct=max_sizing_pct,
        full_go_via=full_go_via,
    )
