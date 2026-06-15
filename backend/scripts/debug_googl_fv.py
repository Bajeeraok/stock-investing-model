"""One-off: trace GOOGL model FV vs street."""
from __future__ import annotations

from signals.fair_value_estimator import (
    _method_peg_blend,
    classify_stock_type,
    estimate_fair_value,
)
from signals.fv_router import route_fair_value

config_guardrails = {
    "street_blend_trigger_below_pct": 0.20,
    "street_blend_trigger_above_pct": 0.12,
    "street_blend_weight": 0.55,
    "street_blend_above_weight": 0.45,
    "street_floor_min_pct": 0.72,
    "analyst_mean_cap_mult": 1.10,
}

info: dict = {}
try:
    from signals.fetcher import build_fundamentals_info

    info = build_fundamentals_info("GOOGL") or {}
    print("=== build_fundamentals_info ===")
    for k in (
        "trailingPE",
        "forwardPE",
        "revenueGrowth",
        "earningsGrowth",
        "profitMargins",
        "debtToEquity",
        "trailingEps",
        "forwardEps",
        "currentPrice",
    ):
        print(f"  {k}: {info.get(k)}")
except Exception as e:
    print("fetcher error:", e)

analyst = 412.0
try:
    from signals.fmp_client import fmp_price_target_consensus

    fmp = fmp_price_target_consensus("GOOGL")
    print("FMP consensus:", fmp)
    if isinstance(fmp, dict) and fmp.get("targetMedian"):
        analyst = float(fmp["targetMedian"])
except Exception as e:
    print("FMP error:", e)

price = float(info.get("currentPrice") or info.get("regularMarketPrice") or 359.68)
ttm_pe = float(info.get("trailingPE") or 22.0)
fwd_pe = float(info.get("forwardPE") or 19.0)

def _pct(v, default):
    if v is None:
        return default
    v = float(v)
    return v * 100 if abs(v) < 5 else v

rev_g = _pct(info.get("revenueGrowth"), 18.0)
earn_g = _pct(info.get("earningsGrowth"), 22.0)
margin = _pct(info.get("profitMargins"), 32.8)
de = float(info.get("debtToEquity") or 0.2)
sector_pe = 28.5
sector_fwd = 24.0
ttm_eps = info.get("trailingEps")
ntm_eps = info.get("forwardEps")

route = route_fair_value(
    "GOOGL", ttm_eps=ttm_eps, ntm_eps=ntm_eps, ttm_pe=ttm_pe, sector="Communication Services"
)
print("\n=== route_fair_value ===")
print(
    f"force_forward_pe={route.force_forward_pe} suppressed={route.fv_suppressed} "
    f"label={route.method_label!r}"
)

r = estimate_fair_value(
    current_price=price,
    ttm_pe=ttm_pe,
    sector_pe=sector_pe,
    revenue_growth_pct=rev_g,
    earnings_growth_pct=earn_g,
    net_margin_pct=margin,
    de_ratio=de,
    forward_pe=fwd_pe,
    sector_forward_pe=sector_fwd,
    analyst_target=analyst,
    guardrails=config_guardrails,
    force_forward_pe=route.force_forward_pe,
)
print("\n=== estimate_fair_value (current) ===")
print(f"price={price:.2f} ttm_pe={ttm_pe} fwd_pe={fwd_pe} analyst={analyst}")
print(f"rev_g={rev_g:.1f}% earn_g={earn_g:.1f}% margin={margin:.1f}%")
print(f"stock_type={r.stock_type} method={r.method_used}")
print(f"fair_value={r.fair_value} discount={r.discount_pct}%")
for n in r.notes:
    print(f"  note: {n}")

raw = _method_peg_blend(
    price,
    ttm_pe,
    sector_pe,
    rev_g,
    earn_g,
    margin,
    de,
    forward_pe=fwd_pe,
    sector_forward_pe=sector_fwd,
)
print(f"\nraw peg_blend (pre-reconcile): {raw:.2f}")
classif = classify_stock_type(ttm_pe, rev_g, earn_g, margin)
print(f"classification: {classif.stock_type.value}")

print("\n=== sensitivity ===")
for street in [395, 412, 420, 425]:
    r2 = estimate_fair_value(
        price,
        ttm_pe,
        sector_pe,
        rev_g,
        earn_g,
        margin,
        de,
        forward_pe=fwd_pe,
        sector_forward_pe=sector_fwd,
        analyst_target=float(street),
        guardrails=config_guardrails,
        force_forward_pe=route.force_forward_pe,
    )
    print(f"  analyst={street}: FV={r2.fair_value} method={r2.method_used}")

# Old logic: no above-street blend (only HIGH_GROWTH below-street)
print("\n=== without above-street blend (legacy) ===")
legacy_gr = dict(config_guardrails)
legacy_gr["street_blend_trigger_above_pct"] = 999.0
r_legacy = estimate_fair_value(
    price,
    ttm_pe,
    sector_pe,
    rev_g,
    earn_g,
    margin,
    de,
    forward_pe=fwd_pe,
    sector_forward_pe=sector_fwd,
    analyst_target=analyst,
    guardrails=legacy_gr,
    force_forward_pe=route.force_forward_pe,
)
print(f"  FV={r_legacy.fair_value} (analyst={analyst})")
