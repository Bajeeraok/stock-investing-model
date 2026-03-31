"""Data models for Thrive Alpha Phase 2."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class SetupType(Enum):
    BREAKOUT = "breakout"
    MEAN_REVERSION = "mean_reversion"
    MOMENTUM_CONTINUATION = "momentum_continuation"
    NO_SETUP = "no_setup"


@dataclass
class FundamentalMetrics:
    ticker: str
    revenue_growth_yoy: Optional[float] = None
    gross_margin: Optional[float] = None
    gross_margin_change: Optional[float] = None
    fcf_yield: Optional[float] = None
    fcf: Optional[float] = None
    eps_beat_rate: Optional[float] = None
    debt_to_equity: Optional[float] = None
    debt_to_equity_change: Optional[float] = None
    guidance_revision: Optional[float] = None
    pe_ratio: Optional[float] = None
    revenue_ttm: Optional[float] = None
    net_income_ttm: Optional[float] = None
    analyst_target: Optional[float] = None
    fetched_at: datetime = field(default_factory=datetime.now)


@dataclass
class IntradayData:
    ticker: str
    interval: str
    df: object  # pd.DataFrame
    current_price: float
    atr: float
    vwap: float
    ma20: float
    ma50: float
    rsi: float
    volume_ratio: float
    resistance: float
    support: float
    fetched_at: datetime = field(default_factory=datetime.now)


@dataclass
class SetupSignal:
    ticker: str
    setup_type: SetupType
    profile: str
    confidence: float
    entry_price: float
    target_1: float
    target_2: float
    stop: float
    rr_ratio: float
    atr: float
    rationale: list
    generated_at: datetime = field(default_factory=datetime.now)
    is_fresh: bool = True


@dataclass
class EntryConviction:
    ticker: str
    profile: str
    action: str
    conviction: str
    suggested_size: float
    entry_zone_low: float
    entry_zone_high: float
    stop: float
    target_1: float
    target_2: float
    fundamental_score: int
    trim_triggers: list
    warnings: list
    rationale: str
