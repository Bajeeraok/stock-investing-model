"""Entry band touch lookup (EOD backtest table)."""
from signals.entry_band_touch import (
    get_entry_band_touch_forecast,
    _spot_vs_band,
    _touched_in_window,
)


def test_spot_vs_band():
    assert _spot_vs_band(110, 100, 105) == "above"
    assert _spot_vs_band(102, 100, 105) == "inside"


def test_touched_in_window():
    import pandas as pd

    close = pd.Series([100.0, 101, 99, 102, 103])
    lows = pd.Series([99.0, 100, 98, 101, 102])
    highs = pd.Series([101.0, 102, 100, 103, 104])
    hit, days = _touched_in_window(lows, highs, close, 0, 100.5, 101.5, 3)
    assert hit is True
    assert days == 1


def test_forecast_lookup():
    table = {
        "windows": {"short": 20, "medium": 63},
        "buckets": {
            "short|UP|above|0-1": {
                "touch_rate_pct": 48.0,
                "median_sessions_to_touch": 9,
                "n": 80,
            },
        },
    }
    fc = get_entry_band_touch_forecast(
        regime="UP",
        price=450.0,
        entry_low=433.0,
        entry_high=440.0,
        atr=5.0,
        horizon="short",
        table=table,
    )
    assert fc is not None
    assert fc["touch_probability_pct"] == 48.0
    assert fc["window_sessions"] == 20
    assert fc["data_source"] == "eod_ohlcv_backtest"
