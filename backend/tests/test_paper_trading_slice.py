"""Paper-trading analysis slice must always load recent[] from CSV, not return summary-only cache."""
from __future__ import annotations

from pathlib import Path

import pytest

from api.routers.dashboard import (
    _paper_trading_slice_stale,
    _refresh_paper_trading_light,
)


def test_paper_trading_slice_stale_when_summary_without_recent():
    assert _paper_trading_slice_stale({"summary": {"completed_n": 12}, "recent": []}) is True
    assert _paper_trading_slice_stale({"summary": {"completed": 5}, "recent": []}) is True
    assert _paper_trading_slice_stale({"equity_curve": [{"date": "2026-01-01"}], "recent": []}) is True


def test_paper_trading_slice_not_stale_when_recent_present():
    pt = {"summary": {"completed_n": 12}, "recent": [{"ticker": "SPY", "date": "2026-03-01"}]}
    assert _paper_trading_slice_stale(pt) is False


def test_paper_trading_slice_not_stale_when_truly_empty():
    assert _paper_trading_slice_stale({"summary": {"completed_n": 0}, "recent": []}) is False


def test_refresh_paper_trading_light_loads_recent_from_csv(tmp_path: Path):
    src = Path(__file__).resolve().parents[1] / "data" / "paper_trades.csv"
    if not src.is_file():
        pytest.skip("sample paper_trades.csv not present")
    dest = tmp_path / "paper_trades.csv"
    dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

    out = _refresh_paper_trading_light({}, [], {"paper_trading": {}}, tmp_path)
    assert isinstance(out.get("recent"), list)
    assert len(out["recent"]) > 0
    assert out["recent"][0].get("ticker")
