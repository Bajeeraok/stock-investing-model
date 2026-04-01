"""Unit tests for macro gate logic (no market data)."""
import pandas as pd

from signals.backtest_ablation import _gate_pass


def test_gate_pass_respects_score_and_bear():
    s_ok = pd.Series({"macro_score": 55.0, "macro_regime": "NEUTRAL"})
    assert _gate_pass(s_ok, min_macro_score=40.0, exclude_bear=True)

    s_low = pd.Series({"macro_score": 35.0, "macro_regime": "NEUTRAL"})
    assert not _gate_pass(s_low, min_macro_score=40.0, exclude_bear=True)

    s_bear = pd.Series({"macro_score": 55.0, "macro_regime": "BEAR"})
    assert not _gate_pass(s_bear, min_macro_score=40.0, exclude_bear=True)

    s_bear_ok_if_disabled = pd.Series({"macro_score": 55.0, "macro_regime": "BEAR"})
    assert _gate_pass(s_bear_ok_if_disabled, min_macro_score=40.0, exclude_bear=False)
