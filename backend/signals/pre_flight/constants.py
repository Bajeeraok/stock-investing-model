"""
Thrive Alpha — Constants & Enums
All shared types, thresholds, and configuration
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, List, Dict


# ─────────────────────────────────────────────
# ENUMS
# ─────────────────────────────────────────────

class AssetType(str, Enum):
    EQUITY_US          = "EQUITY_US"
    EQUITY_ADR         = "EQUITY_ADR"
    EQUITY_SPECULATIVE = "EQUITY_SPECULATIVE"
    EQUITY_DEFENSIVE   = "EQUITY_DEFENSIVE"
    ETF_EQUITY         = "ETF_EQUITY"
    ETF_COMMODITY      = "ETF_COMMODITY"
    ETF_VOLATILITY     = "ETF_VOLATILITY"


class SignalMode(str, Enum):
    AVOID               = "AVOID"
    CONTRARIAN_WATCH    = "CONTRARIAN_WATCH"
    STAGE_1_ACCUMULATE  = "STAGE_1_ACCUMULATE"
    STAGE_2_ACCUMULATE  = "STAGE_2_ACCUMULATE"
    FULL_POSITION       = "FULL_POSITION"
    STAND_DOWN          = "STAND_DOWN"
    BUY                 = "BUY"
    HOLD_WATCH          = "HOLD_WATCH"
    INCOMPATIBLE        = "INCOMPATIBLE"


class CoherenceLevel(str, Enum):
    HIGH        = "HIGH"
    MODERATE    = "MODERATE"
    LOW         = "LOW"
    INCOHERENT  = "INCOHERENT"


class RSISignal(str, Enum):
    OVERSOLD_REVERSAL   = "OVERSOLD_REVERSAL"
    OVERSOLD_FALLING    = "OVERSOLD_FALLING"
    OVERBOUGHT_REVERSAL = "OVERBOUGHT_REVERSAL"
    OVERBOUGHT_MOMENTUM = "OVERBOUGHT_MOMENTUM"
    NEUTRAL             = "NEUTRAL"


class FlagType(str, Enum):
    ERROR = "error"
    WARN  = "warn"
    INFO  = "info"


# ─────────────────────────────────────────────
# THRESHOLDS — tune these to calibrate model
#
# Playbook scenario 3 text must stay aligned with is_regime_shifting in
# signals/pre_flight/signal_fusion.py (strict AND: bear < exit, transition ≥ min,
# pattern > PATTERN_STAGE3_REGIME_SHIFT).
# ─────────────────────────────────────────────

class Thresholds:
    # Contrarian Watch triggers
    BEAR_REGIME_MIN         = 80    # HMM bear % to qualify as deep bear
    OPTIONS_CONTRARIAN_MIN  = 65    # Options sentiment to qualify as contrarian
    DIVERGENCE_SCORE_MIN    = 50    # Options - ML gap flagging conflict

    # Stage progression
    ML_STAGE2_TRIGGER       = 25    # ML % crossing this → Stage 2
    PATTERN_STAGE2_TRIGGER  = 45    # Pattern score crossing this → Stage 2
    ML_FULL_TRIGGER         = 40    # ML % for full position
    PATTERN_FULL_TRIGGER    = 60    # Pattern score for full position

    # Regime shift (must match playbook scenario 3: Pattern Score > this threshold)
    HMM_TRANSITION_MIN      = 30    # HMM transition % indicating shift
    HMM_BEAR_EXIT           = 60    # HMM bear below this = shifting
    PATTERN_STAGE3_REGIME_SHIFT = 50  # Pattern score % required for regime-shift / Stage 3

    # Stand-down
    OPTIONS_FADE_MAX        = 50    # Options below this = thesis fading

    # Transition bonus (BABA fix)
    TRANSITION_BONUS_HMM    = 70    # HMM transition % for bonus
    TRANSITION_BONUS_ML     = 60    # ML % for bonus
    TRANSITION_BONUS_BEAR   = 20    # HMM bear must be below this

    # Coherence (standard deviation thresholds)
    COHERENCE_HIGH          = 15    # stddev < 15 = HIGH
    COHERENCE_MODERATE      = 25    # stddev < 25 = MODERATE
    COHERENCE_LOW           = 35    # stddev < 35 = LOW, else INCOHERENT

    # RSI direction
    RSI_OVERSOLD            = 35
    RSI_OVERBOUGHT          = 70


# ─────────────────────────────────────────────
# WEIGHT PROFILES per asset type
# ─────────────────────────────────────────────

@dataclass
class WeightProfile:
    regime:       float
    pattern:      float
    ml:           float
    options:      float
    insider:      float
    fundamentals: float
    news:         float
    label:        str
    scoring_incompatible: bool = False
    note:         Optional[str] = None
    disabled_layers: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, float]:
        return {
            "regime": self.regime,
            "pattern": self.pattern,
            "ml": self.ml,
            "options": self.options,
            "insider": self.insider,
            "fundamentals": self.fundamentals,
            "news": self.news,
        }


WEIGHT_PROFILES: Dict[AssetType, WeightProfile] = {
    AssetType.EQUITY_US: WeightProfile(
        regime=0.11, pattern=0.15, ml=0.18, options=0.14,
        insider=0.14, fundamentals=0.14, news=0.14,
        label="Standard Equity",
        note=(
            "Rebalanced vs legacy 15/20/10: lower HMM weight (regime also drives a separate bear penalty), "
            "higher fundamentals+news for investor credibility; ML is short-horizon only — see ml_short_horizon in config."
        ),
    ),
    AssetType.EQUITY_SPECULATIVE: WeightProfile(
        regime=0.12, pattern=0.15, ml=0.20, options=0.25,
        insider=0.12, fundamentals=0.06, news=0.10,
        label="Speculative Equity — Options elevated",
        note="High retail sentiment: options flow weighted higher. Fundamentals reduced.",
    ),
    AssetType.EQUITY_DEFENSIVE: WeightProfile(
        regime=0.12, pattern=0.12, ml=0.18, options=0.10,
        insider=0.18, fundamentals=0.18, news=0.12,
        label="Defensive Equity — Fundamentals + Insider elevated",
        note="Low-volatility dividend stocks: fundamentals and insider signals more predictive.",
    ),
    AssetType.EQUITY_ADR: WeightProfile(
        regime=0.15, pattern=0.15, ml=0.28, options=0.22,
        insider=0.00, fundamentals=0.10, news=0.10,
        label="ADR — Insider disabled, ML + Options elevated",
        note="Foreign ADR: insider disclosure unreliable. ML and options flow are primary signals.",
        disabled_layers=["insider"],
    ),
    AssetType.ETF_EQUITY: WeightProfile(
        regime=0.20, pattern=0.20, ml=0.30, options=0.30,
        insider=0.00, fundamentals=0.00, news=0.00,
        label="Equity ETF — Insider + Fundamentals disabled",
        note="ETF: no insider activity, no EPS/PE. Regime, pattern, ML, options only.",
        disabled_layers=["insider", "fundamentals", "news"],
    ),
    AssetType.ETF_COMMODITY: WeightProfile(
        regime=0.30, pattern=0.18, ml=0.18, options=0.22,
        insider=0.00, fundamentals=0.00, news=0.12,
        label="Commodity ETF — Regime + macro news",
        note=(
            "No P/E-style fundamentals or insider. News layer uses commodity/precious-metals lexicon "
            "(GLD/SLV/…); regime + options remain primary."
        ),
        disabled_layers=["insider", "fundamentals"],
    ),
    AssetType.ETF_VOLATILITY: WeightProfile(
        regime=0.00, pattern=0.00, ml=0.00, options=0.00,
        insider=0.00, fundamentals=0.00, news=0.00,
        label="VOLATILITY INSTRUMENT — Standard scoring not applicable",
        scoring_incompatible=True,
        note="Volatility ETFs behave inversely to equity market. Standard ML and regime models produce misleading outputs.",
        disabled_layers=["regime", "pattern", "ml", "options", "insider", "fundamentals", "news"],
    ),
}
