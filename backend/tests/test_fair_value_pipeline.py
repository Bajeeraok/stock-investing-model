"""
Regression lock for signals/fair_value_pipeline.py — the single source of truth for
model fair value, extracted from api/ticker_detail.py so scripts/run_daily.py can reuse
it too. These tests mock the I/O boundary (build_fundamentals_info / get_eps_history_counts
/ route_fair_value) and assert the pipeline's own routing/guardrail/cap behavior, which
previously lived inline in ticker_detail.py and had zero direct test coverage.
"""
from __future__ import annotations

from unittest.mock import patch

from signals.fv_router import FvRoute
from signals.fair_value_pipeline import compute_fair_value


_CONFIG: dict = {}


def _fundamentals(**overrides):
    info = {
        "trailingEps": 3.27,
        "forwardEps": 3.60,
        "forwardPE": 30.0,
        "revenueGrowth": 0.14,
        "earningsGrowth": 0.16,
        "profitMargins": 0.22,
        "debtToEquity": 0.5,
        "targetMeanPrice": 200.0,
        "sector": "Technology",
        "freeCashflow": None,
        "sharesOutstanding": None,
    }
    info.update(overrides)
    fmp_km = {"peRatioTTM": 30.0}
    return info, fmp_km


def test_happy_path_growth_name_produces_fair_value():
    """A plain growth-tier name with no suppression should route through the main estimator."""
    with patch("signals.fetcher.build_fundamentals_info", return_value=_fundamentals()), \
         patch("signals.fv_eps_history.get_eps_history_counts", return_value={"total_quarters": 40, "clean_quarters": 40}), \
         patch("signals.fv_router.route_fair_value", return_value=FvRoute()):
        result = compute_fair_value(_CONFIG, "ACME", 100.0, consensus_median=200.0)

    assert result.error is None
    assert result.fair_value is not None and result.fair_value > 0
    assert result.fv_result is not None
    assert result.fv_result.fv_suppressed is False
    assert result.ttm_pe_used == 30.0
    assert result.analyst_target == 200.0
    assert result.eps_quarters_total == 40
    assert result.eps_quarters_clean == 40


def test_suppressed_route_anchors_to_street_and_flags_reason():
    """Banks/REITs/etc. route through fv_router with fv_suppressed=True — fair value must
    fall back to the analyst consensus target, not a PE-model number, and the reason must
    surface for the UI."""
    route = FvRoute(fv_suppressed=True, fv_suppressed_reason="Bank — P/TBV model needed, not PE.")
    with patch("signals.fetcher.build_fundamentals_info", return_value=_fundamentals()), \
         patch("signals.fv_eps_history.get_eps_history_counts", return_value={"total_quarters": 40, "clean_quarters": 40}), \
         patch("signals.fv_router.route_fair_value", return_value=route):
        result = compute_fair_value(_CONFIG, "SOMEBANK", 100.0, consensus_median=145.0)

    assert result.fair_value == 145.0
    assert result.fv_result is not None
    assert result.fv_result.fv_suppressed is True
    assert result.fv_result.fv_suppressed_reason == "Bank — P/TBV model needed, not PE."
    assert result.fv_result.fv_street_anchored is True
    assert result.fv_result.fv_street_anchor_usd == 145.0


def test_suppressed_route_with_no_analyst_target_yields_no_fair_value():
    """Suppressed with no street anchor at all must not fabricate a $0 fair value as truth —
    fair_value stays None so callers apply their own last-resort fallback."""
    route = FvRoute(fv_suppressed=True, fv_suppressed_reason="Recent spinoff — insufficient history.")
    with patch("signals.fetcher.build_fundamentals_info", return_value=_fundamentals(targetMeanPrice=None)), \
         patch("signals.fv_eps_history.get_eps_history_counts", return_value={"total_quarters": 2, "clean_quarters": 0}), \
         patch("signals.fv_router.route_fair_value", return_value=route):
        result = compute_fair_value(_CONFIG, "NEWCO", 50.0, consensus_median=None, cons_low=None, cons_high=None)

    assert result.fair_value is None
    assert result.fv_result is not None
    assert result.fv_result.fv_suppressed is True


def test_spy_uses_earnings_yield_method_not_pe_estimator():
    """SPY bypasses the PE/growth estimator entirely — verifies the special case survived
    the extraction intact. No consensus supplied, so the extreme-divergence guardrail (which
    is orthogonal to this test) has nothing to anchor to and can't mask the assertion."""
    with patch("signals.fetcher.build_fundamentals_info", return_value=_fundamentals(forwardEps=6.5, targetMeanPrice=None)), \
         patch("signals.fv_eps_history.get_eps_history_counts", return_value={"total_quarters": 999, "clean_quarters": 999}), \
         patch("signals.fv_router.route_fair_value", return_value=FvRoute()):
        result = compute_fair_value(
            {"fair_value": {"risk_free_rate": 0.043, "equity_risk_premium": 0.045}},
            "SPY", 500.0,
        )

    assert result.fv_result is not None
    assert result.fv_result.method_used == "earnings_yield_sp500_etf"
    # EPS 6.5 / (0.043 + 0.045) = ~73.86 — nowhere near spot 500, confirming the PE path
    # (which would anchor near current_price) did NOT run.
    assert result.fair_value < 100.0


def test_extreme_divergence_guardrail_floors_at_street_consensus():
    """When the model output collapses far below street consensus, the pipeline must anchor
    to street rather than surface a broken/implausible number."""
    with patch("signals.fetcher.build_fundamentals_info", return_value=_fundamentals(
                profitMargins=0.01, debtToEquity=3.0, revenueGrowth=0.0, earningsGrowth=0.0,
                forwardPE=None,
            )), \
         patch("signals.fv_eps_history.get_eps_history_counts", return_value={"total_quarters": 40, "clean_quarters": 40}), \
         patch("signals.fv_router.route_fair_value", return_value=FvRoute()):
        # Consensus set absurdly high relative to what a weak-fundamentals PE model would
        # produce, to force the >75%-below-street guardrail to trip.
        result = compute_fair_value(_CONFIG, "WEAKCO", 50.0, consensus_median=1000.0)

    assert result.fair_value is not None
    assert result.fair_value >= 1000.0 * 0.25
    assert result.fv_result is not None
    assert "consensus_floor_override" in (result.fv_result.method_used or "") or \
        any("street" in n.lower() for n in (result.fv_result.notes or []))


def test_broad_index_etf_fair_value_capped_at_120_pct_of_spot():
    """Non-SPY broad index ETFs (e.g. QQQ) still route through the normal PE pipeline but
    must never report fair value more than 20% above spot."""
    with patch("signals.fetcher.build_fundamentals_info", return_value=_fundamentals(
                forwardEps=50.0, forwardPE=6.0,  # would otherwise imply a huge FV via SPY-style yield math
            )), \
         patch("signals.fv_eps_history.get_eps_history_counts", return_value={"total_quarters": 999, "clean_quarters": 999}), \
         patch("signals.fv_router.route_fair_value", return_value=FvRoute()):
        result = compute_fair_value(_CONFIG, "QQQ", 400.0, consensus_median=900.0)

    assert result.fair_value is not None
    assert result.fair_value <= 400.0 * 1.20 + 0.01


def test_pipeline_never_raises_on_internal_failure():
    """A hard failure inside the fundamentals fetch must degrade to fair_value=None with an
    error message, not propagate and kill the caller's batch loop."""
    with patch("signals.fetcher.build_fundamentals_info", side_effect=RuntimeError("FMP down")):
        result = compute_fair_value(_CONFIG, "ANY", 100.0)

    assert result.fair_value is None
    assert result.error is not None and "FMP down" in result.error
