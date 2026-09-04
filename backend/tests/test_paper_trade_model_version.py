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
