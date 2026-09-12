"""model_version survives paper-trade creation and CSV round-trips.

_write_all() rewrites the whole CSV via csv.DictWriter(fieldnames=_FIELDS) — any column
not in _FIELDS is silently dropped on every rewrite. This is exactly the class of bug
already found once for gates_passed (see test_signal_row_gates_sync.py); this test
guards the same pattern for model_version, and confirms fill_outcomes()/mark_to_market()
don't clobber it after it's set at trade-open time.
"""

from __future__ import annotations

from signals.model_version import MODEL_VERSION
from signals.paper_trade_logger import PaperTradeLogger, _result_to_paper_record


def test_new_record_stamped_with_current_model_version():
    row = {
        "ticker": "AAA",
        "close": 100.0,
        "signal": "BUY",
        "st_band": {"low": 95.0, "high": 110.0},
    }
    rec = _result_to_paper_record(row, "2027-03-01")
    assert rec is not None
    assert rec["model_version"] == MODEL_VERSION


def test_model_version_survives_csv_round_trip(tmp_path):
    logger = PaperTradeLogger(data_root=tmp_path)
    row = {
        "ticker": "BBB",
        "close": 50.0,
        "signal": "BUY",
        "st_band": {"low": 45.0, "high": 60.0},
    }
    rec = _result_to_paper_record(row, "2027-03-01")
    logger._write_all([rec])

    reread = logger._read_all()
    assert len(reread) == 1
    assert reread[0]["model_version"] == MODEL_VERSION

    # A later rewrite (mimics fill_outcomes/mark_to_market round-tripping the file)
    # must not drop or blank out the version already on the row.
    mutated = dict(reread[0])
    mutated["actual_price"] = "55.0"
    logger._write_all([mutated])
    reread_again = logger._read_all()
    assert reread_again[0]["model_version"] == MODEL_VERSION


def test_frozen_trade_keeps_its_own_version_even_if_current_bumps(tmp_path, monkeypatch):
    """A trade opened under an older version stays tagged with that version even if
    MODEL_VERSION changes again before the trade closes — matches how entry_mode /
    gate_cleared are already frozen at signal time, not re-evaluated on every read."""
    logger = PaperTradeLogger(data_root=tmp_path)
    row = {
        "ticker": "CCC",
        "close": 75.0,
        "signal": "BUY",
        "st_band": {"low": 70.0, "high": 90.0},
        "model_version": "2025.01.1",
    }
    rec = _result_to_paper_record(row, "2027-03-01")
    assert rec["model_version"] == "2025.01.1"
    logger._write_all([rec])
    reread = logger._read_all()
    assert reread[0]["model_version"] == "2025.01.1"


def test_get_recent_normalizes_blank_model_version_to_legacy(tmp_path):
    logger = PaperTradeLogger(data_root=tmp_path)
    rec = _result_to_paper_record(
        {"ticker": "DDD", "close": 10.0, "signal": "BUY", "st_band": {"low": 9.0, "high": 12.0}},
        "2027-03-01",
    )
    assert rec is not None
    rec["model_version"] = ""
    logger._write_all([rec])
    recent = logger.get_recent(limit=10)
    assert recent[0]["model_version"] == "legacy"


def test_performance_summary_includes_by_model_version(tmp_path):
    logger = PaperTradeLogger(data_root=tmp_path)
    rows = []
    for i, (ver, ret, outcome) in enumerate(
        [
            ("2026.09.1", 5.0, "HIT"),
            ("2026.09.1", -2.0, "MISS"),
            ("legacy", 1.0, "HIT"),
        ]
    ):
        rec = _result_to_paper_record(
            {
                "ticker": f"T{i}",
                "close": 100.0,
                "signal": "BUY",
                "st_band": {"low": 95.0, "high": 110.0},
                "model_version": ver,
            },
            f"2027-01-{i + 1:02d}",
        )
        assert rec is not None
        rec["outcome"] = outcome
        rec["hit_target"] = "1" if outcome == "HIT" else "0"
        rec["return_pct"] = str(ret)
        rec["next_date"] = f"2027-02-{i + 1:02d}"
        rows.append(rec)
    logger._write_all(rows)
    summ = logger.get_performance_summary(min_completed=3, min_actionable=3)
    assert summ["current_model_version"] == MODEL_VERSION
    by_mv = summ.get("summary_by_model_version") or {}
    assert "2026.09.1" in by_mv
    assert by_mv["2026.09.1"]["completed_n"] == 2
    assert "legacy" in by_mv
    assert by_mv["legacy"]["completed_n"] == 1
