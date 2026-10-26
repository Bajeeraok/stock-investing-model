import json

import pandas as pd
import pytest
from fastapi import HTTPException

from api.routers import dashboard as dash


def test_estimates_list_and_download(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    assert dash.estimates_snapshots_list()["count"] == 0
    d = tmp_path / "alpha" / "pit_store" / "fmp_estimates"
    d.mkdir(parents=True)
    pd.DataFrame({"ticker": ["AAPL", "MSFT"], "x": [1, 2]}).to_csv(d / "2026-10-26.csv.gz", index=False)
    out = dash.estimates_snapshots_list()
    assert out["count"] == 1 and out["latest_as_of"] == "2026-10-26" and out["latest_rows"] == 2
    resp = dash.estimates_snapshot_download("2026-10-26.csv.gz")
    assert str(resp.path).endswith("2026-10-26.csv.gz")
    with pytest.raises(HTTPException):
        dash.estimates_snapshot_download("../secrets.env")
    with pytest.raises(HTTPException):
        dash.estimates_snapshot_download("2026-01-01.csv.gz")


def test_eod_snapshot_download_from_disk(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    import signals.cache as cache

    monkeypatch.setattr(cache, "get_eod_snapshot_redis", lambda d: None)
    (tmp_path / "eod").mkdir()
    (tmp_path / "eod" / "2026-10-23.json").write_text(json.dumps({"run_results": []}))
    resp = dash.eod_snapshot_get("2026-10-23", download=True)
    assert "attachment" in resp.headers["content-disposition"]
    assert dash.eod_snapshot_get("2026-10-23")["_meta"]["source"] == "disk"
