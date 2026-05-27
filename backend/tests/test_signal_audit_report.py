"""Phase 3: audit report + CSV export."""
from __future__ import annotations

import json

import pytest

from signals.signal_audit_report import (
    audit_cohort_payload,
    build_audit_report,
    export_records_csv,
    list_audit_records,
)
from signals.signal_audit_store import SignalAuditStore, row_to_signal_event, compute_config_hash


@pytest.fixture
def audit_config(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    cohort_file = tmp_path / "cohort.yaml"
    cohort_file.write_text(
        "cohort_tag: test_cohort\ncategories:\n  etfs:\n    - SPY\n",
        encoding="utf-8",
    )
    return {
        "signal_audit": {
            "enabled": True,
            "cohort_file": str(cohort_file),
            "resolve_outcomes_on_read": False,
            "report": {"enabled": True, "resolve_before_build": False},
        },
        "score": {"buy_min": 65, "sell_max": 35},
    }


def test_export_csv_headers(audit_config, tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    store = SignalAuditStore(data_root=tmp_path)
    event = row_to_signal_event(
        {
            "ticker": "SPY",
            "close": 500.0,
            "signal": "BUY",
            "composite_buy": 70,
            "rsi": 50,
            "regime": "UP",
            "st_band": {"low": 480.0, "high": 520.0},
            "mt_band": {"low": 460.0, "high": 540.0},
            "lt_band": {"low": 400.0, "high": 560.0},
            "retail_status": {"go_no_go": "go"},
        },
        signal_date="2026-05-27",
        signal_ts="2026-05-27T16:00:00",
        run_id="r1",
        cohort_tag="test_cohort",
        market_cap_bucket="etfs",
        config_hash=compute_config_hash(audit_config),
        run_source="run_daily",
    )
    store.insert_event(event)
    csv_text = export_records_csv(audit_config, data_root=tmp_path)
    lines = csv_text.strip().splitlines()
    assert "signal_date" in lines[0] and "ticker" in lines[0]
    assert "SPY" in lines[1]


def test_build_audit_report_writes_files(audit_config, tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    store = SignalAuditStore(data_root=tmp_path)
    event = row_to_signal_event(
        {
            "ticker": "SPY",
            "close": 500.0,
            "signal": "HOLD",
            "composite_buy": 50,
            "rsi": 50,
            "regime": "NEUTRAL",
            "st_band": {"low": 480.0, "high": 520.0},
            "mt_band": {"low": 460.0, "high": 540.0},
            "lt_band": {"low": 400.0, "high": 560.0},
            "retail_status": {"go_no_go": "no_go"},
        },
        signal_date="2026-05-27",
        signal_ts="2026-05-27T16:00:00",
        run_id="r1",
        cohort_tag="test_cohort",
        market_cap_bucket="etfs",
        config_hash=compute_config_hash(audit_config),
        run_source="run_daily",
    )
    store.insert_event(event)
    report = build_audit_report(audit_config, data_root=tmp_path, write_files=True)
    assert report["cohort_tag"] == "test_cohort"
    summary_path = tmp_path / "reports" / "audit_summary.json"
    csv_path = tmp_path / "reports" / "signal_audit_export.csv"
    assert summary_path.exists()
    assert csv_path.exists()
    data = json.loads(summary_path.read_text(encoding="utf-8"))
    assert data["outcome_summary"]["events_total"] == 1


def test_list_audit_records_pagination(audit_config, tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    out = list_audit_records(audit_config, data_root=tmp_path, limit=10, offset=0)
    assert out["cohort_tag"] == "test_cohort"
    assert "records" in out


def test_audit_cohort_payload(audit_config):
    payload = audit_cohort_payload(audit_config)
    assert payload["cohort_size"] == 1
    assert "etfs" in payload["categories"]
