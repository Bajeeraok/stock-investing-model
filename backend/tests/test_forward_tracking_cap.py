"""Forward tracking record cap — keep most recent as_of dates in API response."""
from __future__ import annotations

from signals.forward_tracking import _cap_records_recent, get_forward_tracking


def test_cap_records_keeps_most_recent_dates():
    rows = [
        {"as_of_date": "2026-05-01", "ticker": "SPY", "horizon_days": 5},
        {"as_of_date": "2026-05-10", "ticker": "SPY", "horizon_days": 5},
        {"as_of_date": "2026-05-19", "ticker": "SPY", "horizon_days": 5},
    ]
    capped = _cap_records_recent(rows, 2)
    assert len(capped) == 2
    assert capped[0]["as_of_date"] == "2026-05-19"
    assert capped[1]["as_of_date"] == "2026-05-10"


def test_get_forward_tracking_includes_meta(monkeypatch, tmp_path):
    dates = [f"2026-04-{d:02d}" for d in range(1, 26)]  # 25 days
    snapshots = {}

    def fake_list(_eod_dir):
        return dates

    def fake_load(_eod_dir, d):
        if d not in snapshots:
            snapshots[d] = {
                "run_results": [
                    {"ticker": "SPY", "close": 500.0, "composite_buy": 72, "signal": "BUY"},
                ]
            }
        return snapshots[d]

    monkeypatch.setattr("signals.forward_tracking._list_eod_dates", fake_list)
    monkeypatch.setattr("signals.forward_tracking._load_snapshot", fake_load)

    out = get_forward_tracking(
        data_root=tmp_path,
        tickers=["SPY"],
        horizons=[5],
        max_pairs_per_horizon=10,
        max_records=50,
    )
    assert out.get("meta")
    assert out["meta"]["eod_date_last"] == dates[-1]
    assert out["records"]
    assert max(r["as_of_date"] for r in out["records"]) >= dates[-8]
