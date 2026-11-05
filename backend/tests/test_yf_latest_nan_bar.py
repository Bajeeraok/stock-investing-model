import pandas as pd

from signals import fetcher


def test_empty_today_bar_uses_fast_last_price(monkeypatch):
    idx = pd.to_datetime(["2026-11-02", "2026-11-03", "2026-11-04"])
    frame = pd.DataFrame({"Close": [862.25, 918.2, float("nan")]}, index=idx)
    monkeypatch.setattr(fetcher, "_download_with_crumb_retry", lambda *a, **k: frame)
    monkeypatch.setattr(fetcher, "_fast_last_price", lambda s: 832.78)
    assert fetcher.fetch_yfinance_latest_prices(["GEV"]) == {"GEV": 832.78}
    frame.iloc[-1, 0] = 840.0
    assert fetcher.fetch_yfinance_latest_prices(["GEV"]) == {"GEV": 840.0}
