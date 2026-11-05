import numpy as np
import pandas as pd

from signals.indicators import multi_horizon_scores


def _close(values):
    return pd.Series(values, index=pd.bdate_range("2024-01-01", periods=len(values)))


def test_long_reason_below_ma200_does_not_say_add_on_dip():
    close = _close(list(np.linspace(100, 200, 300)) + list(np.linspace(195, 150, 10)))
    reason = multi_horizon_scores(close)["long_reason"]
    assert "price below MA200" in reason
    assert "add on dip" not in reason and "uptrend intact" not in reason


def test_long_reason_above_ma200_keeps_uptrend_wording():
    reason = multi_horizon_scores(_close(np.linspace(100, 200, 300)))["long_reason"]
    assert "uptrend intact" in reason
