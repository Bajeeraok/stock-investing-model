"""
Tax-Aware Exit Optimizer — flag positions approaching 1-year (LTCG) threshold.
Federal + state (e.g. SC 7%) capital gains. Short-term = ordinary income rates;
long-term = 0/15/20% federal. Recommends hold to threshold vs trim now based on
model confidence. For taxable accounts; optionally filter by account name.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

# LTCG = long-term capital gains (hold 366+ days)
LTCG_THRESHOLD_DAYS = 365
# Flag when this many days or fewer until LTCG
APPROACHING_DAYS = 90

# Default rates (federal + SC 7%). Override via config.
# Short-term: taxed as ordinary income (e.g. 32% federal + 7% SC = 39%)
DEFAULT_ST_FED_PCT = 32.0
DEFAULT_ST_STATE_PCT = 7.0
# Long-term: 0%, 15%, or 20% federal + state
DEFAULT_LT_FED_PCT = 15.0
DEFAULT_LT_STATE_PCT = 7.0


def _parse_date(v: Any) -> date | None:
    if v is None:
        return None
    if isinstance(v, date):
        return v if not isinstance(v, datetime) else v.date()
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, str):
        v = v.strip()[:10]
        if len(v) == 10 and v[4] == "-" and v[7] == "-":
            try:
                return datetime.strptime(v, "%Y-%m-%d").date()
            except ValueError:
                pass
    return None


def _days_held(purchase_date: date | None, as_of: date | None) -> int | None:
    if purchase_date is None or as_of is None:
        return None
    delta = as_of - purchase_date
    return max(0, delta.days)


def tax_aware_exits(
    per_holding: list[dict],
    results: list[dict],
    as_of_date: date | None = None,
    config: dict | None = None,
    taxable_accounts: list[str] | None = None,
) -> dict[str, Any]:
    """
    For each holding with cost_basis and purchase_date (and in a taxable account if filtered),
    compute days to LTCG, after-tax proceeds at short vs long-term rates, and recommendation.

    per_holding: from portfolio_report, each may have ticker, value, cost_basis, gain_loss, purchase_date, account.
    results: from run_signals (for score, regime).
    as_of_date: compute as of this date (default today).
    config: optional { tax_aware_exit: { st_fed_pct, st_state_pct, lt_fed_pct, lt_state_pct, approaching_days } }.
    taxable_accounts: if set, only include holdings whose account is in this list (e.g. ["Taxable"]). None = include all.

    Returns:
      items: list of { ticker, days_held, days_to_ltcg, gain, st_tax, lt_tax, after_tax_now, after_tax_ltcg,
                      tax_savings_if_hold, recommendation, account, score, regime }
      message: optional summary or "Add purchase_date to holdings for tax-aware exits."
    """
    cfg = (config or {}).get("tax_aware_exit") or {}
    st_fed = float(cfg.get("st_fed_pct", DEFAULT_ST_FED_PCT))
    st_state = float(cfg.get("st_state_pct", DEFAULT_ST_STATE_PCT))
    lt_fed = float(cfg.get("lt_fed_pct", DEFAULT_LT_FED_PCT))
    lt_state = float(cfg.get("lt_state_pct", DEFAULT_LT_STATE_PCT))
    approaching_days = int(cfg.get("approaching_days", APPROACHING_DAYS))

    as_of = as_of_date or date.today()
    results_by_ticker = {r["ticker"]: r for r in (results or []) if not r.get("error")}
    items = []

    for h in per_holding or []:
        ticker = h.get("ticker")
        if not ticker:
            continue
        account = h.get("account", "Default")
        if taxable_accounts is not None and account not in taxable_accounts:
            continue
        cost_basis = h.get("cost_basis")
        value = h.get("value")
        if cost_basis is None or value is None:
            continue
        try:
            cost = float(cost_basis)
            val = float(value)
        except (TypeError, ValueError):
            continue
        qty = h.get("quantity") or 1
        gain = val - cost * qty  # cost_basis is per-share
        if gain <= 0:
            continue
        purchase_date = _parse_date(h.get("purchase_date") or h.get("acquisition_date"))
        if purchase_date is None:
            continue
        days_held = _days_held(purchase_date, as_of)
        if days_held is None:
            continue
        days_to_ltcg = max(0, LTCG_THRESHOLD_DAYS - days_held)
        if days_held >= LTCG_THRESHOLD_DAYS:
            continue  # already LTCG; no "approach" recommendation

        st_rate = (st_fed + st_state) / 100.0
        lt_rate = (lt_fed + lt_state) / 100.0
        st_tax = gain * st_rate
        lt_tax = gain * lt_rate
        after_tax_now = gain - st_tax
        after_tax_ltcg = gain - lt_tax
        tax_savings_if_hold = st_tax - lt_tax

        r = results_by_ticker.get(ticker) or {}
        score = r.get("composite_buy")
        regime = r.get("regime", "")

        if days_to_ltcg > approaching_days:
            recommendation = "Hold — LTCG in {} days; consider reviewing again then.".format(days_to_ltcg)
        elif tax_savings_if_hold < 50:
            recommendation = "Within {} days of LTCG; tax savings small (${:,.0f}). Trim if model weak.".format(days_to_ltcg, tax_savings_if_hold)
        else:
            if score is not None and score < 40 and regime == "DOWN":
                recommendation = (
                    "Approaching LTCG in {} days (save ${:,.0f} tax if you hold). "
                    "Model sees downside risk (score {}, {} regime) — consider trimming despite tax."
                ).format(days_to_ltcg, tax_savings_if_hold, int(score), regime)
            else:
                recommendation = (
                    "Hold {} days to LTCG — save ~${:,.0f} in tax. "
                    "Model confidence {} ({})."
                ).format(days_to_ltcg, tax_savings_if_hold, "OK" if (score is None or score >= 50) else "lower", regime or "—")

        items.append({
            "ticker": ticker,
            "days_held": days_held,
            "days_to_ltcg": days_to_ltcg,
            "gain": round(gain, 2),
            "st_tax": round(st_tax, 2),
            "lt_tax": round(lt_tax, 2),
            "after_tax_now": round(after_tax_now, 2),
            "after_tax_ltcg": round(after_tax_ltcg, 2),
            "tax_savings_if_hold": round(tax_savings_if_hold, 2),
            "recommendation": recommendation,
            "account": account,
            "score": round(score, 1) if score is not None else None,
            "regime": regime,
        })

    items.sort(key=lambda x: (x["days_to_ltcg"], -x["tax_savings_if_hold"]))
    message = None
    if not items and per_holding:
        has_cost = any(h.get("cost_basis") for h in per_holding)
        if has_cost:
            message = "Add purchase_date (or acquisition_date) to holdings for tax-aware exit suggestions. Use YYYY-MM-DD in config or Excel upload."

    return {"items": items, "message": message}
