"""EOD rows/payload carry model_version — see signals/model_version.py.

run_daily.py's _eod_payload() builds each saved row via an explicit field allowlist
(not dict(source)), so a new field silently gets dropped on save unless it's added
there — this is exactly the class of bug already found once in paper_trade_logger's
_FIELDS allowlist. This test guards the EOD side of that same pattern.
"""

from __future__ import annotations

import json

from scripts.run_daily import _eod_payload, save_eod_snapshot
from signals.model_version import MODEL_VERSION


def test_eod_payload_stamps_model_version_per_row_and_top_level():
    results = [
        {"ticker": "AAA", "close": 100.0, "composite_buy": 60, "signal": "HOLD"},
        {"ticker": "BBB", "close": 50.0, "composite_buy": 70, "signal": "BUY"},
    ]
    payload = _eod_payload(results)
    assert payload["model_version"] == MODEL_VERSION
    assert len(payload["run_results"]) == 2
    for row in payload["run_results"]:
        assert row["model_version"] == MODEL_VERSION


def test_saved_eod_snapshot_file_has_model_version(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    results = [{"ticker": "CCC", "close": 200.0, "composite_buy": 55, "signal": "HOLD"}]
    save_eod_snapshot(results, date_str="2027-03-01")
    with open(tmp_path / "eod" / "2027-03-01.json") as f:
        data = json.load(f)
    assert data["model_version"] == MODEL_VERSION
    assert data["run_results"][0]["model_version"] == MODEL_VERSION
