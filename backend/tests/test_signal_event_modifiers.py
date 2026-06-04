"""Tests for signal_event_modifiers (Phase C4/C5)."""
from __future__ import annotations

from signals.signal_event_modifiers import (
    apply_catalyst_modifier,
    compute_stress_label,
    enrich_signal_event_modifiers,
)


def test_stress_label_on_st_buy_when_vix_elevated():
    row = {"short_suggestion": "ADD on pullback", "plan_action": "BUY", "signal": "BUY"}
    label = compute_stress_label(row, vix=24.5)
    assert label is not None
    assert "VIX" in label


def test_stress_label_skips_non_buy():
    row = {"short_suggestion": "TRIM", "signal": "SELL"}
    assert compute_stress_label(row, vix=30) is None


def test_catalyst_modifier_bull_regime():
    row = {
        "regime": "UP",
        "composite_buy": 72,
        "catalyst": {
            "active": True,
            "top_event_type": "M&A",
            "top_impact": 3,
            "headline_summary": "Deal announced",
        },
    }
    mod = apply_catalyst_modifier(row)
    assert mod is not None
    assert mod["active"] is True
    assert "Momentum" in mod["headline"]


def test_enrich_patches_retail_subtitle():
    row = {
        "ticker": "TEST",
        "regime": "UP",
        "retail_status": {"dynamic_subtitle": "Hold band"},
        "catalyst": {"active": True, "top_event_type": "FDA_APPROVAL", "top_impact": 3},
    }
    enrich_signal_event_modifiers(row, {}, vix=15)
    assert row.get("catalyst_modifier")
    assert "Catalyst" in row["retail_status"]["dynamic_subtitle"] or "Momentum" in row["retail_status"]["dynamic_subtitle"]
