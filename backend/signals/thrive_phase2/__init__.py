"""
Thrive Alpha Phase 2 — FMP fundamentals gate, intraday setup classification,
ATR targets, signal freshness, and optional 1m (~21d) hit-rate gate.

Use the same `config` dict as the rest of the app (`load_config()`) so `data.fmp_api_key`
and env `FMP_API_KEY` apply automatically.

Example:
    from config_loader import load_config
    from signals.thrive_phase2 import ThriveAlphaPhase2

    engine = ThriveAlphaPhase2(load_config())
    out = engine.analyze("MSFT", fair_value=471.0, profile="long_term", run_backtest=False)
"""
from __future__ import annotations

from .classifier import SetupClassifier
from .models import (
    EntryConviction,
    FundamentalMetrics,
    IntradayData,
    SetupSignal,
    SetupType,
)
from .orchestrator import ThriveAlphaPhase2

__all__ = [
    "ThriveAlphaPhase2",
    "SetupClassifier",
    "SetupType",
    "SetupSignal",
    "IntradayData",
    "FundamentalMetrics",
    "EntryConviction",
]
