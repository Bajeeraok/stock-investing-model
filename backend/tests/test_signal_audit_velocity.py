from signals.signal_audit_store import row_to_signal_event


def test_row_to_signal_event_velocity_fields():
    row = {
        "ticker": "NVDA",
        "close": 100.0,
        "gate_cleared": False,
        "gates_passed": 2,
        "gates_total": 4,
        "velocity_triggered": True,
        "velocity_score": 72.0,
        "track": "velocity",
        "rvol": 2.4,
        "bb_pct_b": 1.05,
        "velocity_reasons": ["RVOL 2.4× avg"],
        "readiness_tier": "warming",
        "readiness_score": 67.0,
    }
    ev = row_to_signal_event(
        row,
        signal_date="2026-05-19",
        signal_ts="2026-05-19T16:00:00",
        run_id="test",
        cohort_tag="audit_100",
        market_cap_bucket="large_cap_tech",
        config_hash="abc",
        run_source="run_daily",
    )
    assert ev is not None
    assert ev["track"] == "velocity"
    assert ev["velocity_triggered"] == 1
    assert ev["rvol"] == 2.4
    assert ev["readiness_tier"] == "warming"
