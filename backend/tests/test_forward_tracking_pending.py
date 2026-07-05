"""Forward tracking pending rows for stale EOD pairs."""
from __future__ import annotations

from signals.forward_tracking import get_forward_tracking


def test_stale_pair_shows_pending(monkeypatch, tmp_path):
    dates = ["2026-07-02", "2026-07-03", "2026-07-04"]

    def fake_list(_eod_dir):
        return dates

    def fake_load(_eod_dir, d):
        return {
            "run_results": [
                {
                    "ticker": "SPY",
                    "close": 500.0,
                    "high": 501.0,
                    "low": 499.0,
                    "ohlcv_last_date": "2026-07-02",
                    "daily_move_pct": 0.0,
                    "composite_buy": 55,
                    "signal": "HOLD",
                },
            ]
        }

    monkeypatch.setattr("signals.forward_tracking._list_eod_dates", fake_list)
    monkeypatch.setattr("signals.forward_tracking._load_snapshot", fake_load)

    out = get_forward_tracking(
        data_root=tmp_path,
        tickers=["SPY"],
        horizons=[1],
        max_pairs_per_horizon=10,
        max_records=50,
    )
    pending = [r for r in out["records"] if r.get("forward_status") == "pending"]
    assert pending, "expected pending row for stale duplicate session"
    assert pending[0]["actual_return_pct"] is None
    assert pending[0]["data_quality"] == "stale_session"

    complete = [r for r in out["records"] if r.get("forward_status") == "complete"]
    assert not complete
