"""
13F institutional delta → conviction filter (Layer 3).

Quarterly SEC 13F snapshots only (~45d filing lag). Used to support or caution
long-term sizing — never as a short-term entry gate trigger.

Filters passive index filers (Vanguard, BlackRock, etc.) from "smart money" delta.
Normalizes net share change vs float and average daily volume when available.
"""
from __future__ import annotations

import re
from typing import Any, Literal

ConvictionVerdict = Literal["supports", "concerns", "neutral", "unknown"]

# Passive / index trackers — rebalancing, not conviction (§ passive trap)
_DEFAULT_PASSIVE_PATTERNS: tuple[str, ...] = (
    r"vanguard",
    r"blackrock",
    r"ishares",
    r"state street",
    r"geode",
    r"schwab",
    r"fidelity",
    r"invesco",
    r"spdr",
    r"index",
    r"tracking",
    r"capital management llc$",
    r"asset management",
    r"wealth management",
)

# Known active / high-conviction managers (boost weight in delta)
_DEFAULT_ACTIVE_HINTS: tuple[str, ...] = (
    r"berkshire",
    r"baupost",
    r"citadel",
    r"renaissance",
    r"tiger global",
    r"coatue",
    r"pershing square",
    r"duquesne",
    r"giverny",
    r"oaktree",
    r"elliott",
    r"third point",
    r"appaloosa",
    r"bridgewater",
)


def _compile_patterns(patterns: tuple[str, ...] | list[str]) -> list[re.Pattern[str]]:
    out: list[re.Pattern[str]] = []
    for p in patterns:
        try:
            out.append(re.compile(str(p), re.I))
        except re.error:
            continue
    return out


def is_passive_filer(name: str, config: dict | None = None) -> bool:
    cfg = (config or {}).get("institutional") or {}
    patterns = cfg.get("passive_filer_patterns") or list(_DEFAULT_PASSIVE_PATTERNS)
    active_hints = cfg.get("active_manager_patterns") or list(_DEFAULT_ACTIVE_HINTS)
    n = (name or "").strip().lower()
    if not n:
        return False
    for pat in _compile_patterns(active_hints):
        if pat.search(n):
            return False
    for pat in _compile_patterns(patterns):
        if pat.search(n):
            return True
    return False


def _filer_weight(name: str, config: dict | None) -> float:
    """Active managers weighted 1.0; passive 0.0; unknown 0.5."""
    if is_passive_filer(name, config):
        return 0.0
    cfg = (config or {}).get("institutional") or {}
    active_hints = cfg.get("active_manager_patterns") or list(_DEFAULT_ACTIVE_HINTS)
    n = (name or "").strip().lower()
    for pat in _compile_patterns(active_hints):
        if pat.search(n):
            return 1.25
    return 0.65


def _rows_from_bundle(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    edgar = bundle.get("edgar_13f") or {}
    rows = list(edgar.get("top_holder_changes") or [])
    if rows:
        return rows
    yahoo = (bundle.get("institutional_ownership") or {}).get("top_holders") or []
    out: list[dict] = []
    for h in yahoo:
        sh = h.get("shares")
        pct_ch = h.get("pct_change_qoq")
        if sh is None or pct_ch is None:
            continue
        try:
            cur = int(float(sh))
            pct = float(pct_ch)
            if abs(pct) < 0.01:
                prior = cur
            else:
                prior = int(round(cur / (1.0 + pct / 100.0)))
            out.append(
                {
                    "filer": h.get("holder") or "Unknown",
                    "shares": cur,
                    "prior_shares": prior,
                    "change_pct": round(pct, 2),
                    "source": "yahoo_pct_change",
                }
            )
        except (TypeError, ValueError, ZeroDivisionError):
            continue
    return out


def compute_institutional_conviction_filter(
    bundle: dict[str, Any] | None,
    *,
    float_shares: float | None = None,
    avg_daily_volume: float | None = None,
    quarter_price_change_pct: float | None = None,
    config: dict | None = None,
) -> dict[str, Any]:
    """
    Model-ready 13F conviction filter.

    Returns verdict supports | concerns | neutral | unknown and score 0–100.
    role=conviction_filter — not an entry gate.
    """
    base = {
        "role": "conviction_filter",
        "verdict": "unknown",
        "conviction_score": 50,
        "net_shares_active": None,
        "net_shares_all": None,
        "pct_of_float": None,
        "pct_of_adv": None,
        "active_filers_increasing": 0,
        "active_filers_decreasing": 0,
        "passive_filers_excluded": 0,
        "buy_the_dip": False,
        "period_ending": None,
        "prior_period_ending": None,
        "source": None,
        "lag_note": (
            "Quarterly 13F snapshot (~45d filing lag after quarter-end). "
            "Conviction filter only — not a daily entry trigger."
        ),
        "detail": "Insufficient 13F holder delta — treat as neutral for sizing.",
    }
    if not bundle:
        return base

    rows = _rows_from_bundle(bundle)
    edgar = bundle.get("edgar_13f") or {}
    if edgar.get("period_ending"):
        base["period_ending"] = edgar.get("period_ending")
        base["prior_period_ending"] = edgar.get("prior_period_ending")
        base["source"] = edgar.get("source") or "sec_edgar_13f"
    elif (bundle.get("institutional_trend") or {}).get("source"):
        base["source"] = (bundle.get("institutional_trend") or {}).get("source")

    if not rows:
        err = edgar.get("error") or (bundle.get("institutional_ownership") or {}).get("error")
        if err:
            base["detail"] = f"13F delta unavailable ({err}) — neutral conviction."
        return base

    net_active = 0.0
    net_all = 0.0
    passive_ex = 0
    active_inc = 0
    active_dec = 0
    weighted_delta = 0.0
    active_rows: list[dict] = []

    for row in rows:
        name = str(row.get("filer") or "")
        cur = row.get("shares")
        prior = row.get("prior_shares")
        if cur is None or prior is None:
            continue
        try:
            delta = int(cur) - int(prior)
        except (TypeError, ValueError):
            continue
        net_all += delta
        w = _filer_weight(name, config)
        if w <= 0:
            passive_ex += 1
            continue
        weighted_delta += delta * w
        net_active += delta
        if delta > 0:
            active_inc += 1
        elif delta < 0:
            active_dec += 1
        active_rows.append(
            {
                "filer": name,
                "net_shares": delta,
                "change_pct": row.get("change_pct"),
                "weight": round(w, 2),
                "passive": False,
            }
        )

    base["net_shares_active"] = int(round(net_active))
    base["net_shares_all"] = int(round(net_all))
    base["passive_filers_excluded"] = passive_ex
    base["active_filers_increasing"] = active_inc
    base["active_filers_decreasing"] = active_dec
    base["top_active_changes"] = sorted(
        active_rows, key=lambda x: abs(x.get("net_shares") or 0), reverse=True
    )[:5]

    if float_shares and float_shares > 0:
        base["pct_of_float"] = round(net_active / float_shares * 100.0, 4)
    if avg_daily_volume and avg_daily_volume > 0:
        base["pct_of_adv"] = round(net_active / avg_daily_volume * 100.0, 2)

    buy_dip = (
        net_active > 0
        and quarter_price_change_pct is not None
        and float(quarter_price_change_pct) < -3.0
    )
    base["buy_the_dip"] = buy_dip

    score = 50.0
    if net_active > 0:
        score += 12.0
    elif net_active < 0:
        score -= 12.0
    if active_inc > active_dec:
        score += 10.0
    elif active_dec > active_inc:
        score -= 10.0
    if buy_dip:
        score += 15.0
    pct_adv = base.get("pct_of_adv")
    if pct_adv is not None:
        if pct_adv >= 5.0 and net_active > 0:
            score += 8.0
        elif pct_adv <= -5.0 and net_active < 0:
            score -= 8.0
    score = max(0.0, min(100.0, score))

    if net_active > 0 and score >= 58:
        verdict: ConvictionVerdict = "supports"
    elif net_active < 0 and score <= 42:
        verdict = "concerns"
    elif active_inc == active_dec == 0 and abs(net_active) < 1:
        verdict = "neutral"
    else:
        verdict = "neutral"

    base["conviction_score"] = int(round(score))
    base["verdict"] = verdict

    parts = [
        f"Active-manager net Δ {net_active:+,} shares (passive filers excluded: {passive_ex})",
    ]
    if base.get("pct_of_float") is not None:
        parts.append(f"{base['pct_of_float']:+.4f}% of float")
    if pct_adv is not None:
        parts.append(f"{pct_adv:+.1f}% of 20d ADV")
    if buy_dip:
        parts.append("buy-the-dip pattern (accumulation while price fell in quarter)")
    parts.append("conviction filter — not an entry gate")
    base["detail"] = ". ".join(parts) + "."

    return base
