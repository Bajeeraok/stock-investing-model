"""Tests for signal audit store (Phase 0/1)."""
from __future__ import annotations

from pathlib import Path

import pytest

from config_loader import get_audit_cohort_tickers, get_dashboard_signal_universe, get_eod_signal_universe
from signals.signal_audit_store import (
    SignalAuditStore,
    compute_config_hash,
    log_signal_audit_from_results,
    persist_daily_signal_logs,
    row_to_signal_event,
)


@pytest.fixture
def audit_config(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    cohort_file = tmp_path / "cohort.yaml"
    cohort_file.write_text(
        """
cohort_tag: test_cohort
categories:
  etfs:
    - SPY
    - QQQ
  tech:
    - AAPL
""",
        encoding="utf-8",
    )
    return {
        "signal_audit": {
            "enabled": True,
            "cohort_file": str(cohort_file),
            "merge_into_signal_universe": True,
            "min_cohort_capture_ratio": 0.0,
        },
        "score": {"buy_min": 65, "sell_max": 35},
        "watchlist": ["SPY"],
        "portfolios": {},
    }


def _sample_row(ticker: str = "SPY") -> dict:
    return {
        "ticker": ticker,
        "close": 500.0,
        "composite_buy": 72.0,
        "signal": "BUY",
        "plan_action": "WATCH",
        "rsi": 55.0,
        "regime": "NEUTRAL",
        "_global_market_regime": "NEUTRAL",
        "ml_short_prob": 0.45,
        "st_band": {"low": 480.0, "high": 520.0},
        "mt_band": {"low": 460.0, "high": 540.0},
        "lt_band": {"low": 400.0, "high": 560.0},
        "retail_status": {
            "go_no_go": "no_go",
            "gates_locked_count": 2,
            "gates": [
                {"id": "valuation", "pass": True},
                {"id": "regime", "pass": False},
                {"id": "momentum", "pass": False},
                {"id": "ml", "pass": True, "visual_status": "marginal"},
            ],
        },
    }


def test_cohort_separate_from_watchlist(audit_config):
    cohort = get_audit_cohort_tickers(audit_config)
    assert set(cohort) == {"SPY", "QQQ", "AAPL"}
    dashboard_uni = get_dashboard_signal_universe(audit_config)
    eod_uni = get_eod_signal_universe(audit_config)
    assert "SPY" in dashboard_uni
    assert "QQQ" in eod_uni
    assert "AAPL" in eod_uni
    assert "AAPL" not in dashboard_uni


def test_row_to_signal_event_maps_gates():
    event = row_to_signal_event(
        _sample_row("SPY"),
        signal_date="2026-05-24",
        signal_ts="2026-05-24T07:30:00-04:00",
        run_id="test-run",
        cohort_tag="test_cohort",
        market_cap_bucket="etfs",
        config_hash="abc123",
        run_source="test",
    )
    assert event is not None
    assert event["ticker"] == "SPY"
    assert event["price_at_signal"] == 500.0
    assert event["st_target"] == 520.0
    assert event["mt_target"] == 540.0
    assert event["go_no_go"] == "no_go"
    assert event["gates_passed"] == 2
    assert event["gates_total"] == 4
    assert event["ml_short_prob"] == 45.0


def test_insert_idempotent(audit_config, tmp_path):
    store = SignalAuditStore(data_root=tmp_path)
    event = row_to_signal_event(
        _sample_row("SPY"),
        signal_date="2026-05-24",
        signal_ts="2026-05-24T07:30:00-04:00",
        run_id="run1",
        cohort_tag="test_cohort",
        market_cap_bucket="etfs",
        config_hash=compute_config_hash(audit_config),
        run_source="test",
    )
    ok1, _ = store.insert_event(event)
    ok2, msg2 = store.insert_event(event)
    assert ok1 is True
    assert ok2 is False
    assert msg2 == "duplicate"
    assert store.count_events(cohort_tag="test_cohort", signal_date="2026-05-24") == 1


def test_log_only_cohort_tickers(audit_config, tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    results = [_sample_row("SPY"), _sample_row("QQQ"), _sample_row("MSFT")]
    out = log_signal_audit_from_results(
        results,
        audit_config,
        date_str="2026-05-24",
        run_source="test",
        data_root=tmp_path,
    )
    assert out["appended"] == 2
    assert out["missing_from_run"] == 1  # AAPL not in results
    store = SignalAuditStore(data_root=tmp_path)
    assert store.count_events(cohort_tag="test_cohort") == 2


def test_build_model_audit_payload_empty_db(audit_config, tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    from signals.signal_audit_store import build_model_audit_payload

    payload = build_model_audit_payload(audit_config, data_root=tmp_path)
    assert payload["enabled"] is True
    assert payload["cohort_size"] == 3
    assert payload["pilot_progress_days"] == 0
    assert "No audit rows yet" in (payload.get("message") or "")


def test_build_model_audit_payload_with_rows(audit_config, tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    from signals.signal_audit_store import SignalAuditStore, build_model_audit_payload, row_to_signal_event, compute_config_hash

    store = SignalAuditStore(data_root=tmp_path)
    event = row_to_signal_event(
        _sample_row("SPY"),
        signal_date="2026-05-24",
        signal_ts="2026-05-24T07:30:00",
        run_id="r1",
        cohort_tag="test_cohort",
        market_cap_bucket="etfs",
        config_hash=compute_config_hash(audit_config),
        run_source="run_daily",
    )
    store.insert_event(event)
    payload = build_model_audit_payload(audit_config, data_root=tmp_path)
    assert payload["pilot_progress_days"] == 1
    assert len(payload["recent_records"]) == 1
    assert payload["breakdown_by_gates"]


def test_confidence_band_falls_back_to_composite(audit_config):
    from signals.signal_audit_store import row_to_signal_event, compute_config_hash

    row = _sample_row("SPY")
    row.pop("retail_status", None)
    row["composite_buy"] = 72.5
    ev = row_to_signal_event(
        row,
        signal_date="2026-05-24",
        signal_ts="2026-05-24T07:30:00",
        run_id="r1",
        cohort_tag="test_cohort",
        market_cap_bucket="etfs",
        config_hash=compute_config_hash(audit_config),
        run_source="run_daily",
    )
    assert ev is not None
    assert ev["confidence_low"] == 68.5
    assert ev["confidence_high"] == 76.5


def test_gate_blocker_breakdown(audit_config, tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    from signals.signal_audit_store import SignalAuditStore, log_signal_audit_from_results

    log_signal_audit_from_results(
        [_sample_row("SPY"), _sample_row("QQQ")],
        audit_config,
        date_str="2026-05-24",
        data_root=tmp_path,
    )
    store = SignalAuditStore(data_root=tmp_path)
    blockers = store.gate_blocker_breakdown("test_cohort")
    assert any(b["gate"] in ("regime", "momentum") for b in blockers)


def test_gate_pass_rate_breakdown(audit_config, tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    from signals.signal_audit_store import SignalAuditStore, log_signal_audit_from_results

    log_signal_audit_from_results(
        [_sample_row("SPY"), _sample_row("QQQ")],
        audit_config,
        date_str="2026-05-24",
        data_root=tmp_path,
    )
    store = SignalAuditStore(data_root=tmp_path)
    rates = store.gate_pass_rate_breakdown("test_cohort")
    assert len(rates) == 4
    assert all("pass_pct" in r and "gate" in r for r in rates)
    val = next(r for r in rates if r["gate"] == "valuation")
    assert val["pass_n"] == 2


def test_build_gate_calibration_guidance():
    from signals.signal_audit_store import build_gate_calibration_guidance

    guidance = build_gate_calibration_guidance(
        gate_pass_rates=[
            {"gate": "valuation", "pass_pct": 5.0},
            {"gate": "momentum", "pass_pct": 25.0},
            {"gate": "regime", "pass_pct": 60.0},
            {"gate": "ml", "pass_pct": 80.0},
        ],
        gate_blockers=[
            {"gate": "valuation", "pct_of_events": 95.0},
            {"gate": "momentum", "pct_of_events": 40.0},
        ],
        actionable_slices={"full_go": {"n": 0}, "go_4_gates": {"n": 0}},
    )
    assert guidance["recommend_loosen_valuation"] is False
    assert guidance["recommend_momentum_review"] is True
    assert any("Valuation blocks" in n for n in guidance["notes"])


def test_dashboard_partial_cohort_skipped(audit_config, tmp_path, monkeypatch):
    """Dashboard refresh (~25/100 overlap) must not write partial audit rows."""
    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    cfg = {
        **audit_config,
        "signal_audit": {
            **audit_config["signal_audit"],
            "log_on_dashboard": True,
            "min_cohort_capture_ratio": 0.90,
        },
    }
    results = [_sample_row("SPY"), _sample_row("QQQ")]
    out = log_signal_audit_from_results(
        results,
        cfg,
        date_str="2026-06-08",
        run_source="dashboard",
        data_root=tmp_path,
    )
    assert out.get("skipped") is True
    assert "below min" in (out.get("reason") or "")
    store = SignalAuditStore(data_root=tmp_path)
    assert store.count_events(cohort_tag="test_cohort", signal_date="2026-06-08") == 0


def test_persist_dashboard_respects_log_on_dashboard_false(audit_config, tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    cfg = {
        **audit_config,
        "signal_audit": {**audit_config["signal_audit"], "log_on_dashboard": False},
    }
    out = persist_daily_signal_logs(
        [_sample_row("SPY"), _sample_row("QQQ"), _sample_row("AAPL")],
        cfg,
        date_str="2026-06-08",
        run_source="dashboard",
        data_root=tmp_path,
    )
    sa = out.get("signal_audit") or {}
    assert sa.get("skipped") is True or sa.get("skipped") == "log_on_dashboard false"


def test_duplicate_run_skips(audit_config, tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    results = [_sample_row("SPY")]
    out1 = log_signal_audit_from_results(results, audit_config, date_str="2026-05-24", data_root=tmp_path)
    out2 = log_signal_audit_from_results(results, audit_config, date_str="2026-05-24", data_root=tmp_path)
    assert out1["appended"] == 1
    assert out2["skipped_duplicate"] == 1
    assert out2["appended"] == 0
