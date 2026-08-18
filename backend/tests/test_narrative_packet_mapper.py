"""narrative_packet_mapper._unlock_conditions() regression."""

from __future__ import annotations

from signals.narrative_packet_mapper import _invalidation, _unlock_conditions
from signals.narrative_waterfall import Gate


def test_unlock_conditions_covers_failed_confidence_gate():
    """Regression: unlock_conditions was built from only the primary 4 raw
    gates (valuation/regime/momentum/ml), so the synthesized confidence gate
    was invisible to it. SignalPacket.validate() requires unlock_conditions
    to cover every failed gate in p.gates, confidence included — so any
    ticker whose confidence gate failed (real-world: NVDA, AMZN) got
    "blocked" with 'unlock_conditions missing failed gate confidence', which
    silently disappeared the Trade Narrative card on the frontend even
    though nothing else about the packet was wrong."""
    gates = [
        Gate("valuation", True, {"text": "ok"}),
        Gate("market_weather", False, {"text": "no"}),
        Gate("momentum_chop", False, {"text": "no"}),
        Gate("ml_probability", True, {"text": "ok"}),
        Gate("confidence", False, {"text": "low"}),
    ]
    conditions = _unlock_conditions(gates)
    failed = [g.name for g in gates if not g.passed]
    for name in failed:
        assert any(name.replace("_", " ") in c.lower() for c in conditions), (
            f"unlock_conditions missing coverage for failed gate '{name}': {conditions}"
        )
    assert any("confidence" in c.lower() for c in conditions)


def test_unlock_conditions_empty_when_all_gates_pass():
    gates = [
        Gate("valuation", True, {"text": "ok"}),
        Gate("market_weather", True, {"text": "ok"}),
        Gate("momentum_chop", True, {"text": "ok"}),
        Gate("ml_probability", True, {"text": "ok"}),
        Gate("confidence", True, {"text": "ok"}),
    ]
    assert _unlock_conditions(gates) == []


def test_owner_invalidation_uses_tactical_stop_when_structural_above_floor():
    horizon = {
        "entry_zone": {"low": 377.87, "high": 396.96},
        "entry_tiers": {"structural_invalidation": {"price": 399.71}},
        "stop_loss": 370.0,
    }
    inv = _invalidation(horizon, "owner", 370.0, 404.92)
    assert inv == 370.0
    assert inv < 377.87
    assert inv < 404.92


def test_owner_invalidation_omitted_when_stop_also_above_floor():
    horizon = {
        "entry_zone": {"low": 377.87, "high": 396.96},
        "entry_tiers": {"structural_invalidation": {"price": 399.71}},
        "stop_loss": 383.0,
    }
    inv = _invalidation(horizon, "owner", 383.0, 404.92)
    assert inv is None
