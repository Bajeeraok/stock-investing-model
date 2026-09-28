"""
fair_value_pipeline.py
=======================
Single source of truth for "what is this ticker's model fair value right now."

Extracted from api/ticker_detail.py's `_build_investor_summary` (the only production
caller before this module existed) so the daily batch job (scripts/run_daily.py) can
compute fair value the SAME way the ticker-detail modal does, instead of running an
independent, cruder PE-band model (see signals/target_bands.py history). Two models
silently disagreeing here previously caused the Signals table and ticker-detail modal
to show contradictory valuation-gate verdicts for the same ticker on the same day.

Pipeline: fetch fundamentals -> derive PE/growth/margin/FCF inputs -> resolve forward PE
-> route through fv_router's sector-specific suppression rules (banks, REITs, asset
managers, insurers, MLPs, pre-revenue biotech, recent IPOs/spinoffs, acquisition targets)
-> fair_value_estimator's multi-method estimate -> extreme-divergence guardrail ->
broad-index-ETF sanity cap.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from signals.fair_value_estimator import (
    FairValueResult,
    compute_index_fair_value,
    estimate_fair_value as estimate_fair_value_full,
)
from signals.fv_router import FvRoute
from signals.providers import MAJOR_INDEX_ETFS


def _safe_float(v: Any) -> float | None:
    """Return float or None; handles NaN/None/strings gracefully."""
    try:
        f = float(v)
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None


def _normalize_growth_pct(raw: float | None) -> float | None:
    """
    FMP's and yfinance's revenueGrowth/earningsGrowth fields are always decimal fractions
    (0.18 = 18% growth), never pre-converted percentages — convert unconditionally. A prior
    version only converted when the value was < 1, assuming anything >= 1 was already a
    percent; that broke on hypergrowth names (NVDA: revenueGrowth=1.06, i.e. +106% YoY),
    where the decimal fraction itself exceeds 1.0, so the old guard silently fed ~1% growth
    into the fair-value model instead of ~106%. The same blind spot hit negative growth too
    (the old guard also required the value to be > 0).
    """
    if raw is None:
        return None
    return raw * 100.0


# Known high-PE growth names (e.g. NVDA 35-40x TTM) — if the data source returns a
# suspiciously low TTM PE (e.g. 17.3 from a split/adjustment error), recompute from
# current price / trailingEps so fair value and fundamentals are not built on bad inputs.
_HIGH_PE_GROWTH = frozenset(
    {"NVDA", "AVGO", "META", "AMD", "TSLA", "CRM", "NOW", "SNOW", "PLTR", "NET", "DDOG",
     "MDB", "CRWD", "PANW", "SNDK", "MU", "AMAT", "LRCX"}
)


def _resolve_forward_pe(
    ttm_pe: float | None,
    forward_pe: float | None,
    current_price: float | None,
    forward_eps_yf: float | None,
) -> tuple[float | None, bool]:
    """
    Sanity-check a forward P/E that's much lower than TTM P/E. This can mean either (a) a
    split-adjustment / GAAP-vs-non-GAAP mismatch between the TTM and forward EPS sources, or
    (b) genuinely fast-ramping forward earnings (real for names like NVDA/AVGO — exactly the
    _HIGH_PE_GROWTH cohort this module already special-cases). The ratio alone can't tell
    these apart, so cross-check against an independently-recomputed forward PE (price /
    yfinance forwardEps): if the two agree, the low number is real and must be kept no
    matter how low it is.

    Returns (resolved_forward_pe, was_discarded).
    """
    if not (
        ttm_pe is not None
        and ttm_pe > 0
        and forward_pe is not None
        and forward_pe > 0
        and forward_pe < ttm_pe * 0.65
        and current_price
    ):
        return forward_pe, False

    if forward_eps_yf and forward_eps_yf > 0:
        forward_pe_yf = round(current_price / forward_eps_yf, 2)
        if abs(forward_pe_yf - forward_pe) / forward_pe <= 0.20:
            return forward_pe_yf, False  # sources agree — low forward P/E is real
        if 18 <= forward_pe_yf <= 60:
            return forward_pe_yf, False  # disagreement, but independent figure is plausible
        return None, True
    return None, True


@dataclass
class FairValuePipelineResult:
    fair_value: float | None
    fv_result: FairValueResult | None
    route: FvRoute | None
    ttm_pe_used: float | None
    forward_pe_used: float | None
    forward_pe_discarded: bool
    sector_pe: float
    sector_forward_pe: float
    analyst_target: float | None
    analyst_target_fmp: float | None
    analyst_target_yahoo: float | None
    trailing_eps: float | None
    ntm_eps: float | None
    forward_eps: float | None
    earnings_growth: float | None
    eps_quarters_total: int | None
    eps_quarters_clean: int | None
    error: str | None = None


def compute_fair_value(
    config: dict,
    ticker: str,
    current_price: float,
    *,
    consensus_median: float | None = None,
    cons_low: float | None = None,
    cons_high: float | None = None,
) -> FairValuePipelineResult:
    """
    Compute model fair value for `ticker` at `current_price`.

    Consensus inputs are parameters, not re-fetched here — callers already have this data
    cheaply (run_daily.py's cached price-target-consensus fetch; ticker_detail.py's response
    dict), so this stays a pure function with respect to analyst consensus and avoids a third
    place independently calling FMP's price-target-consensus endpoint.
    """
    fair_value: float | None = None
    fv_result: FairValueResult | None = None
    earnings_growth: float | None = None
    ttm_pe_used: float | None = None
    forward_pe_used: float | None = None
    forward_pe_discarded = False
    _eps_total: int | None = None
    _eps_clean: int | None = None
    analyst_target_yahoo: float | None = None
    analyst_target_fmp: float | None = _safe_float(consensus_median)
    if analyst_target_fmp is None:
        _cl0 = _safe_float(cons_low)
        _ch0 = _safe_float(cons_high)
        if _cl0 is not None and _ch0 is not None and _cl0 > 0 and _ch0 > 0:
            analyst_target_fmp = (_cl0 + _ch0) / 2.0
    analyst_target: float | None = (
        float(analyst_target_fmp) if analyst_target_fmp and analyst_target_fmp > 0 else None
    )
    trailing_eps: float | None = None
    _ntm_eps: float | None = None
    forward_eps: float | None = None
    info: dict = {}
    sector_pe = 28.0
    sector_forward_pe = 25.0
    _fv_route: FvRoute | None = None
    _error: str | None = None
    _eps_norm = None

    try:
        from signals.fetcher import build_fundamentals_info
        from signals.cache import cached_fundamentals_info

        _fund = cached_fundamentals_info(
            ticker, lambda: build_fundamentals_info(config, ticker, current_price=current_price)
        )
        info = (_fund or {}).get("info") or {}
        fmp_km = (_fund or {}).get("fmp_km")
        ttm_pe = None
        forward_pe = None
        if fmp_km and isinstance(fmp_km, dict):
            ttm_pe = _safe_float(
                fmp_km.get("peRatioTTM") or fmp_km.get("peRatio") or fmp_km.get("trailingPE") or fmp_km.get("priceEarningsRatio")
            )
            forward_pe = _safe_float(fmp_km.get("forwardPE"))

        trailing_eps = _safe_float(info.get("trailingEps"))
        if ttm_pe is None and current_price:
            if trailing_eps and trailing_eps > 0:
                ttm_pe = round(current_price / trailing_eps, 2)
        if ttm_pe is None:
            ttm_pe = _safe_float(info.get("trailingPE"))
        if forward_pe is None:
            forward_pe = _safe_float(info.get("forwardPE"))

        # Strip large one-time/non-operating swings (e.g. a mark-to-market gain on equity
        # investments) out of TTM EPS before it drives ttm_pe — see eps_normalization.py.
        # A no-op for the vast majority of tickers; only fires when a quarter's other-income
        # magnitude is anomalous relative to that quarter's operating income.
        try:
            from signals.fv_eps_history import fetch_quarterly_income
            from signals.cache import cached_quarterly_income
            from signals.eps_normalization import compute_core_ttm_eps

            _q_rows = cached_quarterly_income(
                ticker, lambda: fetch_quarterly_income(config, ticker, limit=4)
            )
            _eps_norm = compute_core_ttm_eps(_q_rows)
            if _eps_norm.adjusted and _eps_norm.core_ttm_eps and _eps_norm.core_ttm_eps > 0 and current_price:
                trailing_eps = _eps_norm.core_ttm_eps
                ttm_pe = round(current_price / trailing_eps, 2)
        except Exception:
            pass

        if (
            ticker.upper() in _HIGH_PE_GROWTH
            and current_price
            and ttm_pe is not None
            and 0 < ttm_pe < 25
        ):
            trailing_eps = _safe_float(info.get("trailingEps"))
            if trailing_eps and trailing_eps > 0:
                ttm_pe_recomputed = round(current_price / trailing_eps, 2)
                if 25 <= ttm_pe_recomputed <= 100:
                    ttm_pe = ttm_pe_recomputed

        forward_pe, forward_pe_discarded = _resolve_forward_pe(
            ttm_pe, forward_pe, current_price, _safe_float(info.get("forwardEps"))
        )

        revenue_growth = _normalize_growth_pct(_safe_float(info.get("revenueGrowth")))
        earnings_growth = _normalize_growth_pct(_safe_float(info.get("earningsGrowth")))
        margin = _safe_float(info.get("profitMargins"))
        if margin is not None and margin < 1:
            margin = margin * 100
        de = _safe_float(info.get("debtToEquity"))
        analyst_target_yahoo = _safe_float(info.get("targetMeanPrice"))
        analyst_target = analyst_target_fmp if analyst_target_fmp and analyst_target_fmp > 0 else analyst_target_yahoo
        fcf = _safe_float(info.get("freeCashflow"))
        shares = _safe_float(info.get("sharesOutstanding"))
        fcf_per_share = (fcf / shares) if (fcf and shares and shares > 0) else None
        forward_eps = _safe_float(info.get("forwardEps"))

        # SPY: earnings-yield model (rf + ERP) on ETF EPS — avoids PE-relative growth logic on an index
        use_spy_yield = (config.get("fair_value") or {}).get("use_earnings_yield_for_spy", True)
        if ticker.upper() == "SPY" and use_spy_yield:
            fv_cfg = config.get("fair_value") or {}
            rf = float(fv_cfg.get("risk_free_rate", 0.043))
            erp = float(fv_cfg.get("equity_risk_premium", 0.045))
            spy_forward_eps = forward_eps
            if spy_forward_eps is None or spy_forward_eps <= 0:
                if forward_pe and forward_pe > 0 and current_price:
                    spy_forward_eps = current_price / forward_pe
                else:
                    te = _safe_float(info.get("trailingEps"))
                    if te and te > 0:
                        spy_forward_eps = te
            if spy_forward_eps and spy_forward_eps > 0:
                fv_sp = compute_index_fair_value(spy_forward_eps, rf, erp, index_level_eps=False)
                disc = round((fv_sp - current_price) / current_price * 100, 1) if current_price else 0.0
                fv_result = FairValueResult(
                    fair_value=fv_sp,
                    stock_type="index_etf",
                    method_used="earnings_yield_sp500_etf",
                    confidence="Medium",
                    discount_pct=disc,
                    analyst_target=analyst_target,
                    notes=[
                        "SPY FV uses earnings-yield (1/(rf+ERP)×EPS per SPY share). "
                        "Tune fair_value.risk_free_rate and equity_risk_premium; not comparable to single-name DCF."
                    ],
                    bear_case=round(fv_sp * 0.85, 2) if fv_sp > 0 else None,
                    methodology_summary=f"SPY index ETF: EPS×(1/(rf+ERP)); rf={rf:.1%}, ERP={erp:.1%}",
                )
                fair_value = fv_sp

        if ttm_pe is not None and ttm_pe > 0:
            ttm_pe_used = ttm_pe
        if forward_pe is not None and forward_pe > 0:
            forward_pe_used = forward_pe

        _ntm_eps = None
        _fwd_eps_raw = forward_eps
        if _fwd_eps_raw and _fwd_eps_raw > 0:
            _ntm_eps = _fwd_eps_raw
        elif forward_pe and forward_pe > 0 and current_price:
            _ntm_eps = current_price / forward_pe

        _sector_str: str | None = str(info["sector"]) if info.get("sector") else None

        try:
            from signals.fv_eps_history import get_eps_history_counts
            from signals.cache import cached_eps_history_counts

            _eps_hist = cached_eps_history_counts(ticker, lambda: get_eps_history_counts(config, ticker))
            _eps_total = (_eps_hist or {}).get("total_quarters")
            _eps_clean = (_eps_hist or {}).get("clean_quarters")
        except Exception:
            pass

        try:
            from signals.fv_router import route_fair_value as _route_fv

            _fv_route = _route_fv(
                ticker=ticker,
                ttm_eps=trailing_eps,
                ntm_eps=_ntm_eps,
                ttm_pe=ttm_pe,
                quarters_of_clean_history=_eps_clean,
                total_quarters_history=_eps_total,
                sector=_sector_str,
            )
        except Exception:
            pass

        _street_anchor_source = (
            "fmp_consensus"
            if analyst_target_fmp and analyst_target_fmp > 0
            else "yahoo_12m_mean"
            if analyst_target_yahoo and analyst_target_yahoo > 0
            else None
        )

        # If suppressed, build a FairValueResult that surfaces the reason instead of a price
        if _fv_route and _fv_route.fv_suppressed and fv_result is None:
            _suppressed_fv = float(analyst_target) if analyst_target and analyst_target > 0 else 0.0
            _street_anchored = _suppressed_fv > 0
            fv_result = FairValueResult(
                fair_value=_suppressed_fv,
                stock_type="suppressed",
                method_used=_fv_route.fv_suppressed_reason or "suppressed",
                confidence="Low",
                discount_pct=(
                    round((_suppressed_fv - current_price) / current_price * 100, 1)
                    if _suppressed_fv > 0 and current_price else 0.0
                ),
                analyst_target=analyst_target,
                notes=list(_fv_route.notes or []),
                bear_case=round(_suppressed_fv * 0.75, 2) if _suppressed_fv > 0 else None,
                methodology_summary=_fv_route.fv_suppressed_reason,
                fv_suppressed=True,
                fv_suppressed_reason=_fv_route.fv_suppressed_reason,
                fv_street_anchored=_street_anchored,
                fv_street_anchor_usd=_suppressed_fv if _street_anchored else None,
                fv_street_anchor_source=_street_anchor_source if _street_anchored else None,
                gap_badge_type=_fv_route.gap_badge_type,
                geopolitical_cap=_fv_route.geopolitical_cap,
                divergence_pct=_fv_route.divergence_pct,
            )
            # Suppressed: keep fair_value as analyst_target for downstream band calcs
            # (better than 0 — avoid killing all bands), but flag it prominently.
            if _suppressed_fv > 0:
                fair_value = _suppressed_fv

        _route_meta_dict: dict = {}
        if _fv_route:
            _route_meta_dict = {
                "notes": list(_fv_route.notes or []),
                "method_label": _fv_route.method_label,
                "gap_badge_type": _fv_route.gap_badge_type,
                "geopolitical_cap": _fv_route.geopolitical_cap,
                "divergence_pct": _fv_route.divergence_pct,
            }

        # Negative TTM EPS with positive analyst consensus — anchor to street
        if (
            fv_result is None
            and (ttm_pe is None or ttm_pe <= 0)
            and trailing_eps is not None
            and trailing_eps <= 0
            and analyst_target is not None
            and analyst_target > 0
        ):
            _neg_notes = [
                "Trailing EPS is non-positive; skipped PE-based fair value to avoid distorted outputs.",
                "Using analyst consensus as interim fair-value anchor until positive TTM earnings normalize PE math.",
            ] + list(_route_meta_dict.get("notes") or [])
            fv_result = FairValueResult(
                fair_value=float(analyst_target),
                stock_type="growth_no_ttm_earnings",
                method_used=_route_meta_dict.get("method_label") or "analyst_consensus_anchor",
                confidence="Low",
                discount_pct=round((float(analyst_target) - current_price) / current_price * 100, 1),
                analyst_target=analyst_target,
                notes=_neg_notes,
                bear_case=round(float(analyst_target) * 0.75, 2),
                methodology_summary="Consensus anchor for loss-making growth names (PE model bypassed).",
                fv_suppressed=False,
                gap_badge_type=_route_meta_dict.get("gap_badge_type") or "METHOD",
                divergence_pct=_route_meta_dict.get("divergence_pct"),
            )
            fair_value = float(analyst_target)

        # Main FV estimation path (route may force forward_pe method)
        if fv_result is None and ttm_pe is not None and ttm_pe > 0 and margin is not None:
            _fv_gr = (config.get("fair_value") or {}).get("guardrails")
            _force_fwd = bool(_fv_route and _fv_route.force_forward_pe)
            fv_result = estimate_fair_value_full(
                current_price=current_price,
                ttm_pe=ttm_pe,
                sector_pe=sector_pe,
                revenue_growth_pct=revenue_growth or 10.0,
                earnings_growth_pct=earnings_growth if earnings_growth is not None else (revenue_growth or 10.0),
                net_margin_pct=margin or 15.0,
                de_ratio=de or 0.5,
                forward_pe=forward_pe,
                sector_forward_pe=sector_forward_pe,
                fcf_per_share=fcf_per_share,
                current_eps=trailing_eps,
                analyst_target=analyst_target,
                guardrails=dict(_fv_gr) if isinstance(_fv_gr, dict) else None,
                force_forward_pe=_force_fwd,
                fv_route_metadata=_route_meta_dict,
            )
            if fv_result and fv_result.fair_value and fv_result.fair_value > 0:
                fair_value = fv_result.fair_value

        if _eps_norm and _eps_norm.adjusted and fv_result is not None:
            existing_notes = list(getattr(fv_result, "notes", []) or [])
            existing_notes.extend(_eps_norm.notes)
            fv_result.notes = existing_notes
    except Exception as exc:
        _error = str(exc)

    # Extreme-divergence guardrail (UI safety): when model FV collapses far below
    # street consensus (FMP primary, Yahoo fallback), anchor to avoid broken copy.
    _street_floor = analyst_target_fmp if analyst_target_fmp and analyst_target_fmp > 0 else analyst_target_yahoo
    if (
        fair_value is not None
        and fair_value > 0
        and _street_floor is not None
        and _street_floor > 0
        and fair_value < _street_floor * 0.25
    ):
        _raw_fv = float(fair_value)
        fair_value = float(_street_floor)
        _floor_label = "FMP consensus" if analyst_target_fmp and analyst_target_fmp > 0 else "Yahoo 12m mean"
        if fv_result is not None:
            notes = list(getattr(fv_result, "notes", []) or [])
            notes.append(
                f"Model fair value was >75% below street ({_floor_label}); anchored for display safety."
            )
            fv_result.notes = notes
            fv_result.fair_value = fair_value
            fv_result.discount_pct = round((fair_value - current_price) / current_price * 100, 1)
            fv_result.bear_case = round(fair_value * 0.75, 2)
            if getattr(fv_result, "method_used", None):
                fv_result.method_used = f"{fv_result.method_used} + consensus_floor_override"
            fv_result.methodology_summary = (
                f"Consensus floor override: raw model FV ${_raw_fv:.2f} "
                f"replaced with street (${fair_value:.2f}, {_floor_label})."
            )
        else:
            fv_result = FairValueResult(
                fair_value=fair_value,
                stock_type="consensus_floor_override",
                method_used="analyst_consensus_floor",
                confidence="Low",
                discount_pct=round((fair_value - current_price) / current_price * 100, 1),
                analyst_target=_street_floor,
                notes=[
                    f"Model fair value was >75% below street; using {_floor_label} as display floor."
                ],
                bear_case=round(fair_value * 0.75, 2),
                methodology_summary=f"Raw model FV ${_raw_fv:.2f} replaced by consensus floor.",
            )

    # Sanity cap for broad index ETFs: earnings-yield FV can inflate when yfinance forwardEps
    # reflects aggregate S&P 500 earnings rather than fund distributions, producing implausible
    # "25%+ undervalued" readings. Cap at 20% above spot and annotate.
    if fair_value is not None and ticker.upper() in MAJOR_INDEX_ETFS and fair_value > 0 and current_price and current_price > 0:
        _fv_cap_ratio = 1.20
        if fair_value > current_price * _fv_cap_ratio:
            _raw_fv = fair_value
            fair_value = round(current_price * _fv_cap_ratio, 2)
            _cap_note = (
                f"Index ETF fair value capped at {_fv_cap_ratio*100:.0f}% of spot "
                f"(raw model: ${_raw_fv:.2f}) — yfinance forwardEps for ETFs can differ from "
                "fund distributions; tune fair_value.risk_free_rate / equity_risk_premium in config."
            )
            if fv_result is not None:
                existing = list(getattr(fv_result, "notes", []) or [])
                existing.append(_cap_note)
                fv_result.notes = existing

    return FairValuePipelineResult(
        fair_value=fair_value,
        fv_result=fv_result,
        route=_fv_route,
        ttm_pe_used=ttm_pe_used,
        forward_pe_used=forward_pe_used,
        forward_pe_discarded=forward_pe_discarded,
        sector_pe=sector_pe,
        sector_forward_pe=sector_forward_pe,
        analyst_target=analyst_target,
        analyst_target_fmp=analyst_target_fmp,
        analyst_target_yahoo=analyst_target_yahoo,
        trailing_eps=trailing_eps,
        ntm_eps=_ntm_eps,
        forward_eps=forward_eps,
        earnings_growth=earnings_growth,
        eps_quarters_total=_eps_total,
        eps_quarters_clean=_eps_clean,
        error=_error,
    )
