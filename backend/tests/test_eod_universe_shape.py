"""Signal Universe shaping — gates/confidence must survive compact cache."""
from __future__ import annotations

from api.routers.dashboard import _shape_universe_rows


def test_shape_universe_uses_frozen_gate_fields():
    raw = [{
        "ticker": "NVDA",
        "composite_buy": 91.0,
        "regime": "UP",
        "signal": "BUY",
        "close": 220.0,
        "gates_passed": 3,
        "gates_total": 4,
        "gates_frozen": True,
        "model_confidence_pct": 75.5,
    }]
    out = _shape_universe_rows(raw, "2026-06-01")
    assert out["total"] == 1
    row = out["rows"][0]
    assert row["gates_passed"] == 3
    assert row["gates_total"] == 4
    assert row["confidence"] == 75.5


def test_shape_universe_from_retail_status_gates():
    raw = [{
        "ticker": "AAPL",
        "composite_buy": 65.0,
        "regime": "UP",
        "signal": "HOLD",
        "retail_status": {
            "entry_mode": "starter_only",
            "gates": [
                {"id": "valuation", "pass": True},
                {"id": "regime", "pass": True},
                {"id": "momentum", "pass": False},
                {"id": "ml", "pass": True},
            ],
        },
        "confidence_mid": 55.0,
    }]
    out = _shape_universe_rows(raw, "2026-06-01")
    row = out["rows"][0]
    assert row["gates_passed"] == 3
    assert row["entry_mode"] == "starter_only"
    assert row["confidence"] == 55.0
