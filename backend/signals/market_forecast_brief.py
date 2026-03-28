"""
Compact market trend brief for the dashboard: combines macro regime, FRED (real yield,
inflation expectations), FMP economic calendar, and cross-asset (DXY, oil USO, gas UNG).

Does not model specific geopolitical headlines (e.g. conflict names); energy stress and
risk-off are inferred from observable prices and volatility. For transparency, the
disclaimer states that shock events are not systematically predicted.
"""
from __future__ import annotations

import datetime as _dt
import logging
from typing import Any

logger = logging.getLogger(__name__)

_HIGH_IMPACT = (
    "cpi", "ppi", "pce", "inflation", "fomc", "fed", "interest rate", "nfp",
    "non-farm", "employment", "gdp", "payrolls", "treasury", "auction",
)


def _by_label(cross_asset: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for a in cross_asset or []:
        if not isinstance(a, dict):
            continue
        lab = (a.get("label") or a.get("ticker") or "").strip()
        if lab:
            out[lab] = a
        t = (a.get("ticker") or "").strip()
        if t:
            out[t] = a
    return out


def _upcoming_macro_events(calendar: list[dict], days: int = 14, max_items: int = 5) -> list[str]:
    """Summarize US + major macro events in the next `days` from FMP calendar."""
    lines: list[str] = []
    cutoff = _dt.date.today() + _dt.timedelta(days=days)
    for ev in calendar or []:
        if not isinstance(ev, dict):
            continue
        name = (ev.get("name") or ev.get("event") or ev.get("title") or "").strip()
        ds = ev.get("date") or ev.get("time") or ""
        if not name:
            continue
        try:
            if isinstance(ds, str) and len(ds) >= 10:
                d = _dt.date.fromisoformat(ds[:10])
            else:
                continue
        except Exception:
            continue
        if d > cutoff or d < _dt.date.today():
            continue
        country = (ev.get("country") or "").upper()
        if country and country not in ("US", "USA", "UNITED STATES", ""):
            continue
        nl = name.lower()
        if any(k in nl for k in _HIGH_IMPACT):
            lines.append(f"{d.strftime('%b %d')}: {name[:72]}")
        if len(lines) >= max_items:
            break
    return lines


def _seasonal_note(month: int) -> str | None:
    """Light-touch calendar seasonality (not a timing model)."""
    if month in (1, 2):
        return "Seasonality: Jan–Feb often see higher volatility after year-end flows; wider bands are normal."
    if month in (5, 6, 7, 8):
        return "Seasonality: Late spring/summer sometimes brings lower volume — gaps can linger vs fair value."
    if month in (9, 10):
        return "Seasonality: Sep–Oct historically volatile; confirm entries with your rules, not price alone."
    if month == 12:
        return "Seasonality: December often has tax-loss selling and rebalancing — noise vs trend can dominate."
    return None


def build_market_forecast_brief(
    config: dict | None,
    macro_regime: str | None,
    real_yield: float | None,
    vix: float | None,
    cross_asset: list[dict],
    economic_calendar: list[dict],
) -> dict[str, Any] | None:
    """
    Returns a small structured brief for UI, or None if nothing to say.
    """
    config = config or {}
    bx = _by_label(cross_asset)
    dxy = bx.get("DXY") or bx.get("DX-Y.NYB")
    oil = bx.get("Oil") or bx.get("USO")
    gas = bx.get("Nat gas") or bx.get("UNG")
    gld = bx.get("Gold") or bx.get("GLD")

    bullets: list[str] = []

    infl_exp: float | None = None
    try:
        from signals.fred_client import get_inflation_expectations
        infl_exp = get_inflation_expectations(config)
    except Exception as e:
        logger.debug("inflation expectations: %s", e)

    if infl_exp is not None:
        bullets.append(
            f"Inflation expectations (10Y breakeven ~{infl_exp:.2f}%): "
            "feeds real yields; when breakeven rises with oil, equities often re-rate."
        )

    if real_yield is not None:
        if real_yield > 2.0:
            bullets.append(
                f"Real yields elevated (~{real_yield:.1f}%): headwind for long-duration growth and gold vs cash/bonds."
            )
        elif real_yield < 0.5:
            bullets.append(
                f"Real yields low (~{real_yield:.1f}%): supports risk assets and gold, but watch for inflation surprises."
            )

    oil_pct = (oil or {}).get("pct_change")
    gas_pct = (gas or {}).get("pct_change")
    if oil_pct is not None and oil_pct > 1.0:
        bullets.append(
            f"Oil (USO) +{oil_pct:.1f}% vs prior close — energy stress often precedes broader risk-off; watch cyclicals."
        )
    elif oil_pct is not None and oil_pct < -1.0:
        bullets.append(
            f"Oil (USO) {oil_pct:.1f}% — softer energy can ease inflation fears short term."
        )

    if gas_pct is not None and abs(gas_pct) >= 1.5:
        bullets.append(
            f"Natural gas (UNG) {gas_pct:+.1f}% — utility/consumer cost angle; not a stock signal by itself."
        )

    dxy_pct = (dxy or {}).get("pct_change")
    if dxy_pct is not None and abs(dxy_pct) >= 0.4:
        bullets.append(
            f"Dollar (DXY) {dxy_pct:+.1f}% — strong dollar can pressure commodities and EM-heavy names."
        )

    if vix is not None:
        if vix > 22:
            bullets.append(f"VIX ~{vix:.0f}: fear elevated — favor smaller size and wider stops until compression.")
        elif vix < 14:
            bullets.append(f"VIX ~{vix:.0f}: complacency risk — shocks can reprice quickly; do not narrow bands blindly.")

    ev_lines = _upcoming_macro_events(economic_calendar, days=14, max_items=4)
    if ev_lines:
        bullets.append("Upcoming macro (US, next ~2 weeks): " + "; ".join(ev_lines[:3]) + ("…" if len(ev_lines) > 3 else ""))

    sn = _seasonal_note(_dt.date.today().month)
    if sn:
        bullets.append(sn)

    # Bias label (educational, rules-based)
    bias = "neutral"
    score = 0
    if macro_regime == "Risk-Off":
        score -= 2
    elif macro_regime == "Risk-On":
        score += 1
    if real_yield is not None and real_yield > 2.0:
        score -= 1
    if vix is not None and vix > 20:
        score -= 1
    if oil_pct is not None and oil_pct >= 1.5:
        score -= 1
    if (gld or {}).get("pct_change") is not None and (gld or {}).get("pct_change", 0) < -0.5 and vix and vix > 18:
        score -= 1
    if score <= -2:
        bias = "cautious"
    elif score >= 1:
        bias = "constructive"
    else:
        bias = "neutral"

    headline = {
        "cautious": "Near-term equity bias: cautious — macro and volatility suggest defense and wider bands.",
        "neutral": "Near-term equity bias: mixed — use your staged entry rules; macro is not one-sided.",
        "constructive": "Near-term equity bias: constructive — but still size to risk; shocks are always possible.",
    }.get(bias, "Near-term equity bias: mixed.")

    if not bullets:
        bullets.append(
            "Limited live macro inputs — add FRED + FMP calendar keys for inflation, yields, and event context."
        )

    return {
        "headline": headline,
        "bias": bias,
        "bullets": bullets[:8],
        "disclaimer": (
            "Educational summary from prices, rates, and scheduled data — not a prediction of wars, "
            "geopolitics, or black swans. Energy and FX moves proxy stress; they do not replace your thesis."
        ),
    }
