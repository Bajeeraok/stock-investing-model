"""Guidelines use real dated events and real numbers — no stale or boilerplate warnings."""
from datetime import date, timedelta

from signals.cross_asset import _upcoming_market_movers, compute_cross_asset_guidelines


def _ev(days_ahead, event, country="US", impact="High"):
    d = (date.today() + timedelta(days=days_ahead)).isoformat()
    return {"date": f"{d} 08:30:00", "event": event, "country": country, "impact": impact}


def test_stale_and_foreign_events_do_not_trigger_heavy_week():
    cal = [
        _ev(-70, "CPI YoY (Jul)", country="CN"),
        _ev(-70, "Fed Interest Rate Decision"),  # stale
        _ev(2, "CPI YoY (Sep)", country="CN"),  # foreign
        _ev(3, "Initial Jobless Claims", impact="Medium"),  # not a market mover
    ]
    assert _upcoming_market_movers(cal) == []
    g = compute_cross_asset_guidelines([], cal)
    assert not any("macro" in x["text"].lower() for x in g)


def test_heavy_week_lists_actual_events():
    cal = [_ev(1, "CPI YoY (Sep)"), _ev(2, "Fed Interest Rate Decision"), _ev(2, "Core CPI MoM (Sep)")]
    movers = _upcoming_market_movers(cal)
    assert [m.split(" (")[0] for m in movers] == ["CPI", "Fed rate decision"]
    text = next(x["text"] for x in compute_cross_asset_guidelines([], cal) if "macro" in x["text"].lower())
    assert "CPI (" in text and "Fed rate decision (" in text and "etc." not in text


def test_cot_line_shows_percent_and_report_date():
    g = compute_cross_asset_guidelines(
        [], [], cot_extremes=[{"label": "Gold", "extreme": "long", "spec_long_pct": 62.4, "report_date": "2026-10-14"}]
    )
    assert any("62% of open interest" in x["text"] and "2026-10-14" in x["text"] for x in g)
