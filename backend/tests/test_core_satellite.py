import json

import numpy as np
import pandas as pd

from signals.alpha.core_satellite import allocation, backtest, regime_series, satellite_validated


def _series(vals):
    return pd.Series(vals, index=pd.bdate_range("2020-01-01", periods=len(vals)), dtype=float)


def test_regime_hysteresis_band_ignores_small_crosses():
    base = [100.0] * 30
    wiggle = [100.5, 99.5] * 5  # inside ±1% band around SMA≈100
    reg = regime_series(_series(base + wiggle), ma_days=20, band_pct=1.0).dropna()
    assert reg.nunique() == 1


def test_regime_flips_on_clear_break_and_is_causal():
    vals = [100.0] * 30 + [90.0] * 10 + [120.0] * 10
    s = _series(vals)
    reg = regime_series(s, ma_days=20, band_pct=1.0)
    assert reg.iloc[35] == 0.0 and reg.iloc[-1] == 1.0
    # appending future bars never changes past states
    assert regime_series(s.iloc[:36], 20, 1.0).iloc[-1] == reg.iloc[35]


def test_allocation_folds_satellite_into_spy_until_validated():
    up = _series(np.linspace(100, 200, 300))
    a = allocation(up, satellite_validated=False)
    assert a["regime"] == "risk_on" and a["core_spy_pct"] == 100 and a["satellite_pct"] == 0
    b = allocation(up, satellite_validated=True)
    assert b["core_spy_pct"] == 80 and b["satellite_pct"] == 20 and b["cash_pct"] == 0


def test_allocation_risk_off_cuts_equity_and_closes_satellite():
    down = _series(list(np.linspace(100, 200, 250)) + list(np.linspace(200, 120, 60)))
    a = allocation(down, satellite_validated=True)
    assert a["regime"] == "risk_off"
    assert a["core_spy_pct"] == 30 and a["satellite_pct"] == 0 and a["cash_pct"] == 70


def test_backtest_reduces_drawdown_in_crash():
    vals = list(np.linspace(100, 150, 260)) + list(np.linspace(150, 75, 120)) + list(np.linspace(75, 140, 200))
    bt = backtest(_series(vals), 2.0)
    assert bt["regime"]["max_dd_pct"] > bt["buy_hold"]["max_dd_pct"]
    assert 30 <= bt["avg_equity_pct"] <= 100


def test_satellite_validated_reads_fundamental_artifact(tmp_path):
    assert satellite_validated(tmp_path) is False
    (tmp_path / "fundamental_validation.json").write_text(json.dumps({"validated": True}))
    assert satellite_validated(tmp_path) is True
