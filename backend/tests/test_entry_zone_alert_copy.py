"""Entry-zone alerts must distinguish band location from gates-clear GO."""
from __future__ import annotations

from scanner.engine import _entry_zone_alert_copy
from scanner.ticker_universe import ScanTier
from scanner.engine import MarketSnapshot


def _snap(price: float = 248.64) -> MarketSnapshot:
    return MarketSnapshot(
        symbol="AMZN",
        price=price,
        iv_rank=40.0,
        iv_percentile=40.0,
        call_put_flow_ratio=1.0,
        price_change_pct=0.5,
        er_days_away=None,
        vix=18.0,
        atr_pct=2.0,
        support_level=None,
        kelly_base=0.02,
        in_watchlist=True,
        scan_tier=ScanTier.TIER1_CORE,
        sector="Tech",
        regime="NEUTRAL",
        regime_confidence=55.0,
    )


def test_entry_zone_zone_only_when_gates_not_clear():
    headline, body, actionable, one_liner, pr, emoji, extra = _entry_zone_alert_copy(
        "AMZN",
        "long",
        "Long-term",
        242.51,
        257.51,
        248.64,
        186.20,
        294.13,
        _snap(),
        {"gates_passed": 1, "gates_total": 4, "go_no_go": "no_go"},
    )
    assert "zone only" in headline.lower()
    assert extra["zoneOnly"] is True
    assert extra["gateCleared"] is False
    assert "4/4" in actionable or "1/4" in actionable
    assert "buy in range" not in actionable.lower()
    assert "Neutral 55%" not in one_liner
    assert pr.name == "MEDIUM"
    assert emoji == "📍"


def test_entry_zone_go_when_gates_clear():
    headline, _, actionable, _, pr, emoji, extra = _entry_zone_alert_copy(
        "AMZN",
        "long",
        "Long-term",
        242.51,
        257.51,
        248.64,
        186.20,
        294.13,
        _snap(),
        {"gates_passed": 4, "gates_total": 4, "go_no_go": "go", "go_ready": True},
    )
    assert extra["gateCleared"] is True
    assert extra["zoneOnly"] is False
    assert "staged add" in actionable.lower()
    assert pr.name == "HIGH"
    assert emoji == "✅"
    assert "zone only" not in headline.lower()
