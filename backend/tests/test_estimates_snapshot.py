import pandas as pd

from signals.alpha import estimates_snapshot as es
from signals.alpha.pit_store import PITStore


def test_flatten_keeps_only_future_quarters_in_order():
    q = [
        {"date": "2026-12-31", "epsAvg": 2.0, "revenueAvg": 10.0, "numAnalystsEps": 20},
        {"date": "2026-06-30", "epsAvg": 1.0},
        {"date": "2027-03-31", "epsAvg": 2.5},
        {"date": "2027-06-30", "epsAvg": 3.0},
    ]
    row = es.flatten(q, {"targetConsensus": 150, "targetHigh": 200}, {"buy": 10, "hold": 3}, "2026-10-25")
    assert row["q1_period"] == "2026-12-31" and row["q1_eps_avg"] == 2.0 and row["q1_n_eps"] == 20
    assert row["q2_period"] == "2027-03-31"
    assert row["pt_consensus"] == 150 and row["grades_buy"] == 10 and row["grades_sell"] is None


def test_run_writes_one_vintage_per_day(tmp_path, monkeypatch):
    monkeypatch.setattr("signals.fmp_client.get_api_key", lambda c: "x")
    monkeypatch.setattr(es, "snapshot_universe", lambda c: ["AAA", "BBB"])
    monkeypatch.setattr(es, "_one", lambda c, t, d: {"ticker": t, "pt_consensus": 1.0})
    out = es.run({}, as_of="2026-10-23", store_root=tmp_path)
    assert out["status"] == "ok" and out["rows"] == 2
    assert es.run({}, as_of="2026-10-23", store_root=tmp_path)["status"] == "exists"
    view = PITStore(tmp_path).as_of_view(es.DATASET, pd.Timestamp.utcnow().tz_localize(None))
    assert set(view.index) == {"AAA", "BBB"}


def test_run_skips_without_key(monkeypatch, tmp_path):
    monkeypatch.setattr("signals.fmp_client.get_api_key", lambda c: None)
    assert es.run({}, store_root=tmp_path)["status"] == "skipped"
