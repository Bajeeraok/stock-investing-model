"""
fair_value_estimator.py
========================
Multi-method fair value estimator for Thrive Alpha.

Replaces the broken single-formula estimate_fair_value() that was producing
garbage results for high-PE growth stocks like AVGO (showed 48.9% undervalued
when it's actually fairly valued / slightly expensive on TTM basis).

Root cause of the bug:
  Old formula used (sector_pe / stock_pe) as a base multiplier.
  For AVGO: sector_pe=28, stock_pe=65 → multiplier = 0.43 → huge discount
  Then quality premium partially recovered it → nonsensical $467 FV.
  The formula was designed for value stocks, not growth/AI semis.

Fix: Classify the stock type first, then choose the appropriate method:

  DEEP_VALUE      PE < 15, slow growth     → PE-relative vs sector
  VALUE           PE 15-25, moderate growth → PE-relative + PEG blend
  GROWTH          PE 25-50, fast growth     → Forward PE + PEG + FCF yield
  HIGH_GROWTH     PE 50+, high growth       → Forward earnings + growth premium
  ETF             Not applicable            → NAV / holdings-based (skip FV)

Usage:
    from fair_value_estimator import estimate_fair_value, classify_stock_type

    fv = estimate_fair_value(
        current_price=313.84,
        ttm_pe=65.0,
        forward_pe=31.0,           # required for HIGH_GROWTH
        sector_pe=28.0,            # TTM sector PE
        sector_forward_pe=25.0,    # forward sector PE
        revenue_growth_pct=24.0,
        earnings_growth_pct=35.0,
        net_margin_pct=36.0,
        de_ratio=0.82,
        fcf_per_share=5.67,        # optional, improves accuracy
    )
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


# ══════════════════════════════════════════════════════════════════════════════
# STOCK TYPE CLASSIFIER
# ══════════════════════════════════════════════════════════════════════════════

class StockType(str, Enum):
    DEEP_VALUE  = "deep_value"    # PE < 15, slow growth, asset-heavy
    VALUE       = "value"         # PE 15-25, steady earnings
    GROWTH      = "growth"        # PE 25-50, above-market growth
    HIGH_GROWTH = "high_growth"   # PE 50+, strong secular growth drivers
    UNKNOWN     = "unknown"


def compute_index_fair_value(
    forward_eps: float,
    risk_free_rate: float,
    equity_risk_premium: float = 0.045,
    *,
    index_level_eps: bool = False,
) -> float:
    """
    Broad market (e.g. SPY) fair value from an earnings-yield / required-return model.

    More appropriate than single-name PE-relative methods for an index ETF. Uses
    fair P/E ≈ 1 / (risk_free_rate + equity_risk_premium).

    Args:
        forward_eps: Forward EPS **per instrument share**. For SPY, use yfinance
            forwardEps or trailingEps for the ETF (already scaled vs the S&P 500 index).
        risk_free_rate: Nominal 10Y Treasury yield as decimal (e.g. 0.043).
        equity_risk_premium: ERP over risk-free (often ~3.5–5% for large caps).
        index_level_eps: If True, ``forward_eps`` is **aggregate S&P 500** forward EPS
            (~270); returns **SPY** fair price (implied index fair value / 10).

    Returns:
        Fair value price per share (rounded).
    """
    if forward_eps <= 0 or risk_free_rate <= 0:
        raise ValueError("forward_eps and risk_free_rate must be positive")
    required_return = risk_free_rate + equity_risk_premium
    if required_return <= 0:
        raise ValueError("risk_free_rate + equity_risk_premium must be positive")
    fair_pe = 1.0 / required_return
    implied = forward_eps * fair_pe
    if index_level_eps:
        implied = implied / 10.0
    return round(float(implied), 2)


@dataclass
class StockClassification:
    stock_type: StockType
    method_used: str
    confidence: str   # Low | Medium | High
    notes: list[str]


def classify_stock_type(
    ttm_pe: float,
    revenue_growth_pct: float,
    earnings_growth_pct: float,
    net_margin_pct: float,
) -> StockClassification:
    """
    Classify stock into valuation category to select the right FV method.
    Match this to your existing asset_classifier.py for consistency.
    """
    notes: list[str] = []

    if ttm_pe <= 0:
        # Negative earnings — can't use PE-based methods
        return StockClassification(
            stock_type=StockType.UNKNOWN,
            method_used="none",
            confidence="Low",
            notes=["Negative or zero TTM earnings — PE-based FV not applicable"],
        )

    if ttm_pe >= 50:
        notes.append("High TTM PE ({:.0f}x) — market pricing in strong forward growth".format(ttm_pe))
        if revenue_growth_pct >= 15 or earnings_growth_pct >= 20:
            notes.append("Growth supports premium: rev +{:.1f}%, earnings +{:.1f}%".format(
                revenue_growth_pct, earnings_growth_pct))
            return StockClassification(
                stock_type=StockType.HIGH_GROWTH,
                method_used="forward_pe_blend",
                confidence="Medium",
                notes=notes,
            )
        else:
            notes.append("High PE without strong growth — potential overvaluation")
            return StockClassification(
                stock_type=StockType.HIGH_GROWTH,
                method_used="forward_pe_blend",
                confidence="Low",
                notes=notes,
            )

    elif ttm_pe >= 25:
        notes.append("Growth range PE ({:.0f}x)".format(ttm_pe))
        return StockClassification(
            stock_type=StockType.GROWTH,
            method_used="peg_blend",
            confidence="Medium",
            notes=notes,
        )

    elif ttm_pe >= 15:
        notes.append("Value range PE ({:.0f}x)".format(ttm_pe))
        return StockClassification(
            stock_type=StockType.VALUE,
            method_used="pe_relative",
            confidence="High",
            notes=notes,
        )

    else:
        notes.append("Deep value PE ({:.0f}x)".format(ttm_pe))
        return StockClassification(
            stock_type=StockType.DEEP_VALUE,
            method_used="pe_relative",
            confidence="High",
            notes=notes,
        )


# ══════════════════════════════════════════════════════════════════════════════
# VALUATION METHODS
# ══════════════════════════════════════════════════════════════════════════════

# YoY growth from feeds can be 100%+ (e.g. NVDA EPS). Uncapped PEG math then implies
# fair P/E > 150 and multiplies fair value far above analyst consensus.
MAX_GROWTH_PCT_FOR_VALUATION = 42.0


def _growth_for_valuation(revenue_growth_pct: float, earnings_growth_pct: float) -> float:
    g = max(revenue_growth_pct, earnings_growth_pct)
    return min(g, MAX_GROWTH_PCT_FOR_VALUATION)


def _apply_fair_value_guardrails(
    fv: float,
    current_price: float,
    analyst_target: Optional[float],
) -> tuple[float, list[str]]:
    """
    Cap systematic inflation: extreme PEG + quality premium can push FV far above
    consensus. Analyst 12m mean is a retail-friendly ceiling; spot cap catches bad/missing consensus.
    """
    notes: list[str] = []
    if fv <= 0 or current_price <= 0:
        return fv, notes

    out = fv
    # 1) Consensus ceiling (Yahoo targetMeanPrice): allow at most +10% vs mean
    if analyst_target and analyst_target > 0:
        soft = analyst_target * 1.10
        if out > soft:
            out = round(soft, 2)
            notes.append(
                "Fair value capped at +10% vs analyst 12m mean — model was above consensus."
            )

    # 2) Hard cap on implied upside vs spot (NVDA-class when consensus is stale/missing)
    max_upside = 0.52
    spot_ceiling = round(current_price * (1 + max_upside), 2)
    if out > spot_ceiling:
        out = spot_ceiling
        notes.append(
            "Fair value capped vs current price (max +{:.0f}% implied upside).".format(max_upside * 100)
        )

    return out, notes


def _method_pe_relative(
    current_price: float,
    ttm_pe: float,
    sector_pe: float,
    net_margin_pct: float,
    de_ratio: float,
) -> float:
    """
    For VALUE and DEEP_VALUE stocks.
    Base: sector_pe / stock_pe adjustment (valid when PE is in normal range).
    Adds quality premium for high margins / low debt.

    Examples: JPM, KO, JNJ, IBM
    """
    pe_adj  = sector_pe / ttm_pe if ttm_pe > 0 else 1.0
    quality = _quality_premium(net_margin_pct, de_ratio)
    return round(current_price * pe_adj * (1 + quality), 2)


def _method_peg_blend(
    current_price: float,
    ttm_pe: float,
    sector_pe: float,
    revenue_growth_pct: float,
    earnings_growth_pct: float,
    net_margin_pct: float,
    de_ratio: float,
    forward_pe: Optional[float] = None,
    sector_forward_pe: Optional[float] = None,
) -> float:
    """
    For GROWTH stocks (PE 25-50).
    Blends PE-relative (TTM vs sector) with PEG normalization.
    When forward_pe + sector_forward_pe are set, the PEG leg uses **forward** P/E as the
    denominator (aligned with how megacaps trade) and tethers to a forward-PE-relative anchor.

    Examples: MSFT, AAPL, AMD
    """
    # Weight: 40% PE-relative, 60% PEG-normalized
    pe_fv = _method_pe_relative(current_price, ttm_pe, sector_pe, net_margin_pct, de_ratio)

    growth = _growth_for_valuation(revenue_growth_pct, earnings_growth_pct)
    fair_peg_pe = growth * 1.0   # PEG=1 → fair PE ≈ growth rate
    quality = _quality_premium(net_margin_pct, de_ratio)

    use_fwd = (
        forward_pe is not None and forward_pe > 0
        and sector_forward_pe is not None and sector_forward_pe > 0
    )

    if use_fwd:
        peg_adj = fair_peg_pe / forward_pe
        peg_fv = round(current_price * peg_adj, 2)
        fwd_anchor_fv = round(
            current_price * (sector_forward_pe / forward_pe) * (1 + quality * 0.5),
            2,
        )
        peg_lo, peg_hi = fwd_anchor_fv * 0.88, fwd_anchor_fv * 1.38
        peg_fv = min(max(peg_fv, peg_lo), peg_hi)
    else:
        peg_adj = fair_peg_pe / ttm_pe if ttm_pe > 0 else 1.0
        peg_fv = round(current_price * peg_adj, 2)
        peg_lo, peg_hi = pe_fv * 0.88, pe_fv * 1.38
        peg_fv = min(max(peg_fv, peg_lo), peg_hi)

    blended = round(pe_fv * 0.4 + peg_fv * 0.6, 2)
    return blended


def _method_forward_pe_blend(
    current_price: float,
    ttm_pe: float,
    forward_pe: float,
    sector_forward_pe: float,
    revenue_growth_pct: float,
    earnings_growth_pct: float,
    net_margin_pct: float,
    de_ratio: float,
    fcf_per_share: Optional[float] = None,
    current_eps: Optional[float] = None,
) -> float:
    """
    For HIGH_GROWTH stocks (PE 50+): AVGO, NVDA, META, etc.

    TTM PE comparison is misleading for these — the market prices in
    forward earnings growth, not trailing.

    Method: blend of three signals
      40%  Forward PE vs sector forward PE  (what market is paying today)
      40%  PEG using forward earnings growth (growth-adjusted fair PE)
      20%  FCF yield anchor (if available)  (cash generation quality)

    Examples: AVGO, NVDA, GOOGL, META
    """
    quality = _quality_premium(net_margin_pct, de_ratio)

    # Signal 1: Forward PE relative to sector forward PE
    # AVGO: fwd_pe=31, sector_fwd_pe=25 → adj=0.81 → slight discount to sector on fwd basis
    fwd_pe_adj = sector_forward_pe / forward_pe if forward_pe > 0 else 1.0
    fwd_pe_fv  = round(current_price * fwd_pe_adj * (1 + quality), 2)

    # Signal 2: PEG using forward earnings growth
    # Fair PEG for high-quality semis/tech ~1.25 — 1.5 overstates vs consensus when growth is capped high
    growth      = _growth_for_valuation(revenue_growth_pct, earnings_growth_pct)
    fair_peg    = 1.25
    fair_fwd_pe = growth * fair_peg
    peg_adj     = fair_fwd_pe / forward_pe if forward_pe > 0 else 1.0
    peg_fv      = round(current_price * peg_adj * (1 + quality * 0.5), 2)
    peg_lo, peg_hi = fwd_pe_fv * 0.80, fwd_pe_fv * 1.35
    peg_fv = min(max(peg_fv, peg_lo), peg_hi)

    # Signal 3: FCF yield anchor (optional)
    # Fair FCF yield for high-quality tech: ~2.5-3.5%
    if fcf_per_share and fcf_per_share > 0:
        target_fcf_yield = 0.028   # 2.8% target FCF yield for quality tech
        fcf_fv = round(fcf_per_share / target_fcf_yield, 2)
        # Blend: 40% fwd PE, 40% PEG, 20% FCF
        blended = round(fwd_pe_fv * 0.40 + peg_fv * 0.40 + fcf_fv * 0.20, 2)
    else:
        # Without FCF: 50% fwd PE, 50% PEG
        blended = round(fwd_pe_fv * 0.50 + peg_fv * 0.50, 2)

    return blended


def _quality_premium(net_margin_pct: float, de_ratio: float) -> float:
    """
    Quality premium based on margins and balance sheet strength.
    Caps at 8% to prevent overweighting.
    """
    q = 0.0
    if net_margin_pct > 15: q += 0.02
    if net_margin_pct > 25: q += 0.02   # stacks
    if net_margin_pct > 35: q += 0.015  # stacks
    if de_ratio < 0.3:      q += 0.025
    elif de_ratio < 0.8:    q += 0.015
    elif de_ratio < 1.5:    q += 0.005
    return min(q, 0.08)   # cap at 8%


# ══════════════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class FairValueResult:
    fair_value: float
    stock_type: str
    method_used: str
    confidence: str
    discount_pct: float        # positive = undervalued, negative = overvalued
    analyst_target: Optional[float]
    notes: list[str]
    # Transparency: bear case and one-line methodology so users can interrogate FV vs lt_band
    bear_case: Optional[float] = None   # e.g. FV * 0.60; conservative downside
    methodology_summary: Optional[str] = None


def estimate_fair_value(
    current_price: float,
    ttm_pe: float,
    sector_pe: float,
    revenue_growth_pct: float,
    earnings_growth_pct: float,
    net_margin_pct: float,
    de_ratio: float,
    # Optional but strongly recommended for HIGH_GROWTH stocks
    forward_pe: Optional[float] = None,
    sector_forward_pe: Optional[float] = None,
    fcf_per_share: Optional[float] = None,
    current_eps: Optional[float] = None,
    analyst_target: Optional[float] = None,
) -> FairValueResult:
    """
    Classify the stock and apply the appropriate valuation method.

    Args:
        current_price:        Latest close price
        ttm_pe:               Trailing twelve months P/E ratio
        sector_pe:            TTM P/E of the sector (e.g. Technology = 28-30)
        revenue_growth_pct:   YoY revenue growth %
        earnings_growth_pct:  YoY earnings/EPS growth %
        net_margin_pct:       Net profit margin %
        de_ratio:             Debt/Equity ratio
        forward_pe:           Forward P/E (next 12m estimates) — used for HIGH_GROWTH; for GROWTH, PEG leg when set
        sector_forward_pe:    Sector forward P/E — pairs with forward_pe for growth names
        fcf_per_share:        Free cash flow per share — improves HIGH_GROWTH accuracy
        current_eps:          TTM EPS — used for sanity checks
        analyst_target:       Consensus analyst 12m price target — used as guardrail

    Returns:
        FairValueResult with fair_value, method, confidence, and discount %
    """
    classification = classify_stock_type(
        ttm_pe=ttm_pe,
        revenue_growth_pct=revenue_growth_pct,
        earnings_growth_pct=earnings_growth_pct,
        net_margin_pct=net_margin_pct,
    )

    notes = list(classification.notes)

    if classification.stock_type == StockType.UNKNOWN:
        return FairValueResult(
            fair_value=current_price,   # default to current price
            stock_type=StockType.UNKNOWN.value,
            method_used="none",
            confidence="Low",
            discount_pct=0.0,
            analyst_target=analyst_target,
            notes=notes + ["Cannot estimate FV without positive earnings"],
            bear_case=None,
            methodology_summary=None,
        )

    # ── Select method based on stock type ──────────────────────────────────

    if classification.stock_type in (StockType.DEEP_VALUE, StockType.VALUE):
        fv = _method_pe_relative(
            current_price, ttm_pe, sector_pe, net_margin_pct, de_ratio)
        method = "pe_relative"

    elif classification.stock_type == StockType.GROWTH:
        fv = _method_peg_blend(
            current_price, ttm_pe, sector_pe,
            revenue_growth_pct, earnings_growth_pct,
            net_margin_pct, de_ratio,
            forward_pe=forward_pe,
            sector_forward_pe=sector_forward_pe,
        )
        if forward_pe is not None and forward_pe > 0 and sector_forward_pe is not None and sector_forward_pe > 0:
            method = "peg_blend (40% TTM PE-relative + 60% PEG on forward P/E)"
        else:
            method = "peg_blend (40% PE-relative + 60% PEG on TTM P/E)"

    else:  # HIGH_GROWTH
        if forward_pe is None or sector_forward_pe is None:
            # Fall back to PEG blend if forward PE not provided
            notes.append(
                "WARNING: forward_pe or sector_forward_pe not provided. "
                "Using PEG blend — pass forward PE for better accuracy on high-growth stocks.")
            fv = _method_peg_blend(
                current_price, ttm_pe, sector_pe,
                revenue_growth_pct, earnings_growth_pct,
                net_margin_pct, de_ratio,
                forward_pe=None,
                sector_forward_pe=None,
            )
            method = "peg_blend_fallback (forward_pe missing)"
            classification = StockClassification(
                stock_type=classification.stock_type,
                method_used=classification.method_used,
                confidence="Low",
                notes=classification.notes,
            )
        else:
            fv = _method_forward_pe_blend(
                current_price, ttm_pe, forward_pe, sector_forward_pe,
                revenue_growth_pct, earnings_growth_pct,
                net_margin_pct, de_ratio, fcf_per_share, current_eps)
            method = "forward_pe_blend (40% fwd PE + 40% PEG + 20% FCF)" if fcf_per_share else \
                     "forward_pe_blend (50% fwd PE + 50% PEG)"

    fv, guard_notes = _apply_fair_value_guardrails(fv, current_price, analyst_target)
    notes.extend(guard_notes)

    # After caps: optional flag if still far from consensus (stale target or edge case)
    if analyst_target:
        divergence = abs(fv - analyst_target) / analyst_target * 100
        if divergence > 40:
            notes.append(
                "Model FV (${:.2f}) diverges {:.1f}% from analyst consensus (${:.2f}) — "
                "treat with caution".format(fv, divergence, analyst_target))
        elif divergence > 20:
            notes.append(
                "Model FV (${:.2f}) vs analyst consensus (${:.2f}) — "
                "{:.1f}% gap, review inputs".format(fv, analyst_target, divergence))

    discount_pct = round((fv - current_price) / current_price * 100, 1)

    # Bear case: conservative downside (FV * 0.60) so users see gap vs fair value
    bear_case = round(fv * 0.60, 2) if fv > 0 else None
    methodology_summary = (
        f"{classification.stock_type.value}: {method}. "
        f"Bear case ${bear_case:.2f} (FV×0.6) vs fair ${fv:.2f} — gap reflects method assumptions."
    ) if bear_case is not None else None

    return FairValueResult(
        fair_value=fv,
        stock_type=classification.stock_type.value,
        method_used=method,
        confidence=classification.confidence,
        discount_pct=discount_pct,
        analyst_target=analyst_target,
        notes=notes,
        bear_case=bear_case,
        methodology_summary=methodology_summary,
    )


# ══════════════════════════════════════════════════════════════════════════════
# CONVENIENCE: plain float version for backward compatibility with
# horizon_entry_calculator.py  — drop-in replacement
# ══════════════════════════════════════════════════════════════════════════════

def estimate_fair_value_simple(
    current_price: float,
    ttm_pe: float,
    sector_pe: float,
    revenue_growth_pct: float,
    net_margin_pct: float,
    de_ratio: float,
    forward_pe: Optional[float] = None,
    sector_forward_pe: Optional[float] = None,
    fcf_per_share: Optional[float] = None,
    analyst_target: Optional[float] = None,
    earnings_growth_pct: Optional[float] = None,
) -> float:
    """
    Drop-in replacement for the old estimate_fair_value().
    Returns just the float for use in horizon_entry_calculator.py.
    """
    result = estimate_fair_value(
        current_price=current_price,
        ttm_pe=ttm_pe,
        sector_pe=sector_pe,
        revenue_growth_pct=revenue_growth_pct,
        earnings_growth_pct=earnings_growth_pct if earnings_growth_pct is not None else revenue_growth_pct,
        net_margin_pct=net_margin_pct,
        de_ratio=de_ratio,
        forward_pe=forward_pe,
        sector_forward_pe=sector_forward_pe,
        fcf_per_share=fcf_per_share,
        analyst_target=analyst_target,
    )
    return result.fair_value


# ══════════════════════════════════════════════════════════════════════════════
# TEST CASES
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":

    def print_result(ticker: str, result: FairValueResult, current_price: float) -> None:
        tag = "UNDERVALUED" if result.discount_pct > 5 else \
              "OVERVALUED"  if result.discount_pct < -5 else "FAIRLY VALUED"
        print("  Ticker       : {}".format(ticker))
        print("  Current      : ${:.2f}".format(current_price))
        print("  Fair Value   : ${:.2f}".format(result.fair_value))
        print("  Discount     : {:.1f}%  →  {}".format(result.discount_pct, tag))
        print("  Stock Type   : {}".format(result.stock_type))
        print("  Method       : {}".format(result.method_used))
        print("  Confidence   : {}".format(result.confidence))
        if result.analyst_target:
            print("  Analyst Tgt  : ${:.2f}".format(result.analyst_target))
        for note in result.notes:
            print("  NOTE         : {}".format(note))
        print()

    sep = "=" * 62

    # ── AVGO: HIGH_GROWTH — the bug case ─────────────────────────────────
    print(sep)
    print("AVGO (Broadcom) — HIGH_GROWTH semiconductor")
    print(sep)
    avgo = estimate_fair_value(
        current_price       = 313.84,
        ttm_pe              = 65.0,
        sector_pe           = 28.0,
        revenue_growth_pct  = 24.0,
        earnings_growth_pct = 35.0,
        net_margin_pct      = 36.0,
        de_ratio            = 0.82,
        forward_pe          = 31.0,
        sector_forward_pe   = 25.0,
        fcf_per_share       = 5.67,
        analyst_target      = 420.31,
    )
    print_result("AVGO", avgo, 313.84)

    # ── GOOGL: GROWTH ─────────────────────────────────────────────────────
    print(sep)
    print("GOOGL (Alphabet) — GROWTH")
    print(sep)
    googl = estimate_fair_value(
        current_price       = 299.86,
        ttm_pe              = 22.4,
        sector_pe           = 28.5,
        revenue_growth_pct  = 18.0,
        earnings_growth_pct = 22.0,
        net_margin_pct      = 32.8,
        de_ratio            = 0.2,
        forward_pe          = 19.0,
        sector_forward_pe   = 24.0,
        analyst_target      = 220.0,
    )
    print_result("GOOGL", googl, 299.86)

    # ── JPM: VALUE ────────────────────────────────────────────────────────
    print(sep)
    print("JPM (JPMorgan) — VALUE")
    print(sep)
    jpm = estimate_fair_value(
        current_price       = 245.0,
        ttm_pe              = 13.5,
        sector_pe           = 14.0,
        revenue_growth_pct  = 8.0,
        earnings_growth_pct = 10.0,
        net_margin_pct      = 28.0,
        de_ratio            = 1.2,
        analyst_target      = 275.0,
    )
    print_result("JPM", jpm, 245.0)

    # ── NVDA: HIGH_GROWTH (no FCF provided) ───────────────────────────────
    print(sep)
    print("NVDA (Nvidia) — HIGH_GROWTH (no FCF)")
    print(sep)
    nvda = estimate_fair_value(
        current_price       = 118.0,
        ttm_pe              = 50.0,
        sector_pe           = 28.0,
        revenue_growth_pct  = 122.0,
        earnings_growth_pct = 145.0,
        net_margin_pct      = 55.0,
        de_ratio            = 0.41,
        forward_pe          = 25.0,
        sector_forward_pe   = 24.0,
        analyst_target      = 175.0,
    )
    print_result("NVDA", nvda, 118.0)

    # ── Old vs new comparison for AVGO ────────────────────────────────────
    print(sep)
    print("OLD vs NEW fair value — AVGO")
    print(sep)
    # Simulating old broken formula
    old_pe_adj     = 28.0 / 65.0          # 0.43 — wrong direction for high-PE stock
    old_peg        = 65.0 / 24.0          # 2.71
    old_growth_adj = 1.0 + max(0, (1.5 - old_peg) * 0.05)   # 1.0 (no bonus)
    old_quality    = 0.03 + 0.02 + 0.015  # margin + debt
    old_fv         = round(313.84 * old_pe_adj * old_growth_adj * (1 + old_quality), 2)
    print("  Old formula FV : ${:.2f}  (WRONG — inflated by quality premium compensating bad PE adj)".format(old_fv))
    print("  New formula FV : ${:.2f}  (uses forward PE blend)".format(avgo.fair_value))
    print("  Analyst target : $420.31")
    print("  Simply Wall St : $297.38 (DCF)")
    print()
    print("  Verdict: AVGO is roughly FAIRLY VALUED to slightly expensive on TTM")
    print("  basis. Forward earnings growth justifies current price if AI thesis holds.")
