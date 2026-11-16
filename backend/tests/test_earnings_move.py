import pandas as pd
import numpy as np

from signals.earnings_log import pre_close_date, score_entry
from signals.earnings_move import K80, forecast, reaction_index, report_timing, typical_move


def _dates():
    return pd.DatetimeIndex(pd.bdate_range("2026-01-05", periods=10))


def test_timing():
    assert report_timing(pd.Timestamp("2026-11-17 16:00", tz="America/New_York")) == "amc"
    assert report_timing(pd.Timestamp("2026-01-14 08:00", tz="America/New_York")) == "bmo"
    assert report_timing(pd.Timestamp("2026-01-14 00:00")) is None


def test_reaction_window_amc_spans_next_session():
    d = _dates()
    assert reaction_index(d, pd.Timestamp("2026-01-07 16:05")) == (2, 3)


def test_reaction_window_bmo_is_report_day():
    d = _dates()
    assert reaction_index(d, pd.Timestamp("2026-01-07 07:30")) == (1, 2)


def test_typical_move_blend():
    assert abs(typical_move([0.0312] * 8, 0.0154) - 0.0304) < 1e-9
    assert typical_move([0.05] * 3, None) is None
    assert typical_move([], 0.0308) > 0.06


def test_forecast_bands_and_pre_close_date():
    rng = np.random.default_rng(0)
    idx = pd.bdate_range("2024-01-01", periods=400)
    close = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.015, 400))), index=idx)
    f = forecast(close, None, 100.0)
    assert f["range80_low"] < f["range50_low"] < 100 < f["range50_high"] < f["range80_high"]
    assert abs(f["move80_pct"] / f["typical_move_pct"] - K80) < 0.05
    assert pre_close_date(pd.Timestamp("2026-11-17 16:00")).isoformat() == "2026-11-17"
    assert pre_close_date(pd.Timestamp("2026-11-16 08:00")).isoformat() == "2026-11-13"


def test_score_entry():
    e = {"move50_pct": 4.0, "move80_pct": 8.0, "typical_move_pct": 4.1, "options": {"move_pct": 7.0}}
    s = score_entry(e, 100.0, 92.5)
    assert s["actual_move_pct"] == -7.5 and not s["in50"] and s["in80"] and s["in_options"] is False
