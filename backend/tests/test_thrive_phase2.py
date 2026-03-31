"""Smoke tests for Thrive Alpha Phase 2 (no network)."""
from __future__ import annotations

import pandas as pd

from signals.thrive_phase2 import SetupClassifier, SetupType
from signals.thrive_phase2.models import IntradayData
from signals.thrive_phase2._constants import merge_phase2_config


def test_merge_phase2_config_defaults():
    m = merge_phase2_config({})
    assert m["min_hit_rate_1m"] == 0.65
    assert "breakout" in m["atr_config"]


def test_classifier_detects_breakout_conditions():
    d = IntradayData(
        ticker="SPY",
        interval="1h",
        df=pd.DataFrame(),
        current_price=100.0,
        atr=1.0,
        vwap=99.0,
        ma20=98.0,
        ma50=97.0,
        rsi=60.0,
        volume_ratio=2.0,
        resistance=100.5,
        support=95.0,
    )
    st, conf, rationale = SetupClassifier().classify(d, hmm_bear_pct=50.0)
    assert st in SetupType
    assert 0.0 <= conf <= 1.0
    assert isinstance(rationale, list)


def test_no_setup_when_scores_low():
    d = IntradayData(
        ticker="X",
        interval="1h",
        df=pd.DataFrame(),
        current_price=50.0,
        atr=5.0,
        vwap=50.0,
        ma20=50.0,
        ma50=50.0,
        rsi=50.0,
        volume_ratio=1.0,
        resistance=200.0,
        support=10.0,
    )
    st, conf, _ = SetupClassifier().classify(d, hmm_bear_pct=50.0)
    assert st == SetupType.NO_SETUP
