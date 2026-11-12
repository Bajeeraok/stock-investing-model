import pandas as pd

from signals.fv_own_history import own_history_pe


def _rows(n=24, eps=10.0):
    d = pd.date_range("2020-01-15", periods=n, freq="QS-JAN") + pd.Timedelta(days=14)
    return [{"date": str(x.date()), "eps_actual": eps} for x in d]


def _px(level=800.0):
    idx = pd.bdate_range("2019-01-01", "2026-01-30")
    return pd.Series(level, index=idx)


def test_fv_is_ttm_eps_times_median_pe():
    out = own_history_pe(_rows(), _px(800.0))
    assert out["ttm_eps"] == 40.0
    assert out["median_pe"] == 20.0
    assert out["fair_value"] == 800.0


def test_needs_enough_history():
    assert own_history_pe(_rows(4), _px()) is None
    assert own_history_pe(_rows(), _px().iloc[-200:]) is None


def test_negative_ttm_eps_returns_none():
    assert own_history_pe(_rows(eps=-1.0), _px()) is None


def test_skips_forward_rows_without_actuals():
    rows = _rows() + [{"date": "2026-04-15", "eps_actual": None}]
    assert own_history_pe(rows, _px())["fair_value"] == 800.0
