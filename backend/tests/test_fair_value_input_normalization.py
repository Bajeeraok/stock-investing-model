"""
Regression tests for the NVDA fair-value bug: growth-field normalization silently broke
for hypergrowth names (decimal fraction >= 1.0), and the forward-PE sanity check discarded
genuinely-low-but-real forward P/E values. See docs/signals/RETAIL_DATA_SURFACING.md and
api/ticker_detail.py::_normalize_growth_pct / _resolve_forward_pe.
"""
from __future__ import annotations

import pytest

from api.ticker_detail import _normalize_growth_pct, _resolve_forward_pe


def test_normalize_growth_pct_small_decimal():
    assert _normalize_growth_pct(0.18) == 18.0


def test_normalize_growth_pct_hypergrowth_above_one():
    """NVDA-class case: revenueGrowth=1.06 means +106% YoY, not +1.06%."""
    assert _normalize_growth_pct(1.059) == pytest.approx(105.9)


def test_normalize_growth_pct_negative():
    """A declining-earnings name (-15% YoY) must not be flattened to near-zero."""
    assert _normalize_growth_pct(-0.15) == -15.0


def test_normalize_growth_pct_none_passthrough():
    assert _normalize_growth_pct(None) is None


def test_resolve_forward_pe_keeps_agreeing_low_value():
    """NVDA case: forward_pe and the independently-recomputed forward_pe_yf agree at
    ~14.9x — a genuinely low forward P/E from fast-ramping earnings, must be kept."""
    resolved, discarded = _resolve_forward_pe(
        ttm_pe=29.16, forward_pe=14.90, current_price=230.36, forward_eps_yf=15.4581
    )
    assert discarded is False
    assert resolved == 14.9


def test_resolve_forward_pe_prefers_plausible_disagreeing_recompute():
    """Sources disagree, but the independently-recomputed figure lands in the plausible
    band — prefer it over the original (likely bad) forward_pe."""
    resolved, discarded = _resolve_forward_pe(
        ttm_pe=38.0, forward_pe=17.0, current_price=100.0, forward_eps_yf=2.5,  # -> 40.0
    )
    assert discarded is False
    assert resolved == 40.0


def test_resolve_forward_pe_discards_when_recompute_missing():
    resolved, discarded = _resolve_forward_pe(
        ttm_pe=38.0, forward_pe=17.0, current_price=100.0, forward_eps_yf=None,
    )
    assert discarded is True
    assert resolved is None


def test_resolve_forward_pe_discards_implausible_disagreement():
    resolved, discarded = _resolve_forward_pe(
        ttm_pe=38.0, forward_pe=17.0, current_price=100.0, forward_eps_yf=14.0,  # -> 7.14, disagrees, implausible
    )
    assert discarded is True
    assert resolved is None


def test_resolve_forward_pe_noop_when_not_much_lower_than_ttm():
    """Ratio not below the 0.65 trigger — pass forward_pe through unchanged."""
    resolved, discarded = _resolve_forward_pe(
        ttm_pe=30.0, forward_pe=25.0, current_price=100.0, forward_eps_yf=3.5,
    )
    assert discarded is False
    assert resolved == 25.0


def test_resolve_forward_pe_noop_when_inputs_missing():
    resolved, discarded = _resolve_forward_pe(
        ttm_pe=None, forward_pe=17.0, current_price=100.0, forward_eps_yf=2.5,
    )
    assert discarded is False
    assert resolved == 17.0
