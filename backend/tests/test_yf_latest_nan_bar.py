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


def test_history_fetchers_fill_blank_last_close(monkeypatch):
    idx = pd.bdate_range("2026-01-01", periods=300)
    closes = [100.0] * 299 + [float("nan")]
    frame = pd.DataFrame({"Close": closes, "High": closes, "Low": closes, "Volume": [1.0] * 300}, index=idx)
    monkeypatch.setattr(fetcher, "_download_with_crumb_retry", lambda *a, **k: frame.copy())
    monkeypatch.setattr(fetcher, "_fetch_index_etf_via_ticker_history", lambda *a, **k: (None, None))
    monkeypatch.setattr(fetcher, "_fetch_index_etf_ohlcv_dataframe", lambda *a, **k: None)
    monkeypatch.setattr(fetcher, "_cache_get", lambda k: (False, None))
    monkeypatch.setattr(fetcher, "_cache_set", lambda k, v: None)
    monkeypatch.setattr(fetcher, "_fast_last_price", lambda s: 90.0)
    assert fetcher.fetch_ohlcv("GEV", "1y").iloc[-1] == 90.0
    assert fetcher.fetch_ohlcv_with_volume("GEV", "1y")[0].iloc[-1] == 90.0
    df = fetcher.fetch_ohlcv_dataframe("GEV", "1y")
    assert df["close"].iloc[-1] == 90.0 and df["high"].iloc[-1] == 90.0 and len(df) == 300
