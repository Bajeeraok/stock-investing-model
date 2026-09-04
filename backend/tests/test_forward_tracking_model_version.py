"""model_version flows from EOD snapshot rows through forward_tracking records and the
summary_by_model_version breakdown — the whole point being that a win-rate number can be
isolated to the current gate/band/regime logic instead of blending it with signals
produced under earlier versions (see signals/model_version.py).
"""

from __future__ import annotations

from signals.forward_tracking import get_forward_tracking
from signals.model_version import MODEL_VERSION


def test_model_version_flows_into_records_and_summary(monkeypatch, tmp_path):
    # 40 business-day-ish dates (skip real calendar, just sequential day-of-month strings
    # is fine here since forward_tracking works off the snapshot filename list directly)
    dates = [f"2027-{m:02d}-{d:02d}" for m in (1, 2) for d in range(1, 21)]  # 40 days
    date_idx = {d: i for i, d in enumerate(dates)}
    snapshots = {}
    legacy_cutoff = dates[10]  # first 10 dates = legacy, rest = current version
    # With horizon=20 and 40 dates, as_of indices 0..19 pair up — some land before
    # legacy_cutoff (index 10) and some after, giving both versions in the 20d summary.

    def fake_list(_eod_dir):
        return dates

    def fake_load(_eod_dir, d):
        if d not in snapshots:
            # Close must be a function of the *continuous* list position, not day-of-month —
            # day-of-month resets every 20 entries here, which collided exactly with the
            # horizon=20 pairing and made every as_of/next pair land on an identical close
            # (flagged as a stale/duplicate session instead of a real forward return).
            close = 100.0 + date_idx[d] * 0.5
            version = "2025.01.1" if d < legacy_cutoff else MODEL_VERSION
            snapshots[d] = {
                "run_results": [
                    {
                        "ticker": "MVTEST",
                        "close": close,
                        "high": close + 1.0,
                        "low": close - 1.0,
                        "composite_buy": 72,
                        "signal": "BUY",
                        "model_version": version,
                    },
                ]
            }
        return snapshots[d]

    monkeypatch.setattr("signals.forward_tracking._SNAPSHOT_MEM_CACHE", {})
    monkeypatch.setattr("signals.forward_tracking._list_eod_dates", fake_list)
    monkeypatch.setattr("signals.forward_tracking._load_snapshot", fake_load)

    out = get_forward_tracking(
        data_root=tmp_path,
        tickers=["MVTEST"],
        horizons=[1, 20],
        max_pairs_per_horizon=20,
        max_records=200,
    )

    records = out["records"]
    assert records
    for r in records:
        as_of = r["as_of_date"]
        expected = "2025.01.1" if as_of < legacy_cutoff else MODEL_VERSION
        assert r.get("model_version") == expected

    by_version = out["summary_by_model_version"]
    assert MODEL_VERSION in by_version
    assert "2025.01.1" in by_version
    assert by_version[MODEL_VERSION]["n_observations"] > 0
    assert by_version["2025.01.1"]["n_observations"] > 0

    assert out["meta"]["current_model_version"] == MODEL_VERSION


def test_model_version_missing_reports_as_legacy(monkeypatch, tmp_path):
    dates = [f"2027-02-{d:02d}" for d in range(1, 26)]
    snapshots = {}

    def fake_list(_eod_dir):
        return dates

    def fake_load(_eod_dir, d):
        if d not in snapshots:
            day = int(d.split("-")[-1])
            close = 200.0 + day * 0.3
            snapshots[d] = {
                "run_results": [
                    {
                        "ticker": "MVLEGACY",
                        "close": close,
                        "high": close + 1.0,
                        "low": close - 1.0,
                        "composite_buy": 60,
                        "signal": "HOLD",
                        # no model_version — simulates a pre-versioning EOD snapshot
                    },
                ]
            }
        return snapshots[d]

    monkeypatch.setattr("signals.forward_tracking._SNAPSHOT_MEM_CACHE", {})
    monkeypatch.setattr("signals.forward_tracking._list_eod_dates", fake_list)
    monkeypatch.setattr("signals.forward_tracking._load_snapshot", fake_load)

    out = get_forward_tracking(
        data_root=tmp_path,
        tickers=["MVLEGACY"],
        horizons=[20],
        max_pairs_per_horizon=20,
        max_records=200,
    )

    assert all(r.get("model_version") is None for r in out["records"])
    assert "legacy" in out["summary_by_model_version"]
    assert MODEL_VERSION not in out["summary_by_model_version"]
