"""SPY/QQQ via Ticker.history arrive tz-aware; stock bars are tz-naive. They must align by date."""
from __future__ import annotations

import numpy as np
import pandas as pd

from signals import fetcher


def test_index_etf_history_is_tz_naive_and_aligns_with_stock_bars(monkeypatch):
    days = pd.bdate_range("2024-01-02", periods=300)
    aware = days.tz_localize("America/New_York")
    frame = pd.DataFrame({"Close": np.linspace(400, 500, len(days)), "Volume": 1}, index=aware)
    monkeypatch.setattr(fetcher, "_history_with_crumb_retry", lambda *a, **k: frame.copy())

    hist = fetcher._fetch_index_etf_history_frame("SPY", "2y")
    assert hist is not None and hist.index.tz is None

    stock = pd.Series(1.0, index=days)
    aligned = hist["Close"].reindex(stock.index)
    assert aligned.notna().all()
