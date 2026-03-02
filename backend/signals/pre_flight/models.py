"""
Thrive Alpha — Data Models
All input/output dataclasses used across the engine
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime

from .constants import (
    AssetType, SignalMode, CoherenceLevel, RSISignal,
    FlagType, WeightProfile
)


# ─────────────────────────────────────────────
# INPUT MODELS
# ─────────────────────────────────────────────

@dataclass
class SignalInput:
    """
    Raw signal inputs for a single ticker.
    All scores are 0-100. None = data unavailable.
    """
    ticker: str

    # HMM regime state probabilities (must sum to ~100)
    hmm_bull_prob:       float = 0.0
    hmm_transition_prob: float = 0.0
    hmm_bear_prob:       float = 0.0

    # Layer scores (0-100, None = N/A)
    pattern_score:     Optional[float] = None
    ml_probability:    Optional[float] = None
    options_sentiment: Optional[float] = None
    insider_activity:  Optional[float] = None
    fundamentals:      Optional[float] = None

    # RSI for direction signal
    rsi_current:  Optional[float] = None
    rsi_previous: Optional[float] = None

    # Price context
    current_price: Optional[float] = None
    price_bands:   Optional[Dict[str, float]] = None

    # Optional metadata
    earnings_date: Optional[str] = None
    days_since_earnings: Optional[int] = None
    post_earnings_return_pct: Optional[float] = None
    post_earnings_volume_ratio: Optional[float] = None
    note:          Optional[str] = None


@dataclass
class AssetMeta:
    """Metadata about an asset from the registry."""
    ticker:                  str
    name:                    str
    asset_type:              AssetType
    sector:                  str
    country:                 str = "US"
    beta:                    Optional[float] = None
    insider_data_reliable:   bool = True
    fundamentals_applicable: bool = True
    ml_applicable:           bool = True
    macro_sensitive:         bool = False
    macro_driver:            Optional[str] = None
    geopolitical_risk:       bool = False
    sentiment_amplified:     bool = False
    insider_note:            Optional[str] = None
    fundamentals_note:       Optional[str] = None
    ml_note:                 Optional[str] = None


# ─────────────────────────────────────────────
# OUTPUT MODELS
# ─────────────────────────────────────────────

@dataclass
class PreFlightFlag:
    flag_type: FlagType
    message:   str

    def to_dict(self) -> Dict:
        return {"type": self.flag_type.value, "message": self.message}


@dataclass
class ClassificationResult:
    """Output from asset classifier."""
    ticker:         str
    asset_type:     AssetType
    name:           str
    sector:         str
    weight_profile: WeightProfile
    flags:          List[PreFlightFlag]
    is_scoreable:   bool
    meta:           Optional[AssetMeta] = None

    def to_dict(self) -> Dict:
        return {
            "ticker":        self.ticker,
            "asset_type":    self.asset_type.value,
            "name":          self.name,
            "sector":        self.sector,
            "is_scoreable":  self.is_scoreable,
            "weight_profile": self.weight_profile.as_dict(),
            "weight_label":  self.weight_profile.label,
            "flags":         [f.to_dict() for f in self.flags],
            "flag_count":    len(self.flags),
        }


@dataclass
class DivergenceResult:
    """Signal divergence between options and ML."""
    score:            float    # Absolute gap between options and ML
    label:            str      # EXTREME / HIGH / MODERATE / LOW
    is_high_conflict: bool
    direction:        str      # OPTIONS_BULLISH_ML_BEARISH or vice versa

    def to_dict(self) -> Dict:
        return {
            "score": round(self.score, 1),
            "label": self.label,
            "is_high_conflict": self.is_high_conflict,
            "direction": self.direction,
        }


@dataclass
class BlendResult:
    """Contrarian-weighted composite score."""
    blended_score: float
    method:        str    # CONTRARIAN_BLEND or STANDARD_BLEND
    weights_used:  Dict[str, float]
    note:          str

    def to_dict(self) -> Dict:
        return {
            "blended_score": round(self.blended_score, 1),
            "method":        self.method,
            "weights_used":  self.weights_used,
            "note":          self.note,
        }


@dataclass
class RegimeTransitionResult:
    """Forward-looking regime shift probability."""
    shift_probability: float
    days_estimate:     str
    label:             str

    def to_dict(self) -> Dict:
        return {
            "shift_probability": round(self.shift_probability, 1),
            "days_estimate":     self.days_estimate,
            "label":             self.label,
        }


@dataclass
class CoherenceResult:
    """Signal coherence assessment."""
    level:              CoherenceLevel
    std_dev:            Optional[float]
    mean:               Optional[float]
    spread:             Optional[float]
    active_layer_count: int
    active_layers:      List[Dict]
    tradeable:          bool
    is_contrarian:      bool
    message:            str

    def to_dict(self) -> Dict:
        return {
            "level":              self.level.value,
            "std_dev":            round(self.std_dev, 1) if self.std_dev else None,
            "mean":               round(self.mean, 1) if self.mean else None,
            "spread":             round(self.spread, 1) if self.spread else None,
            "active_layer_count": self.active_layer_count,
            "tradeable":          self.tradeable,
            "is_contrarian":      self.is_contrarian,
            "message":            self.message,
        }


@dataclass
class TransitionBonusResult:
    """Transition momentum bonus for BABA-type situations."""
    bonus_active:    bool
    upgrade:         Optional[str] = None
    position_bonus:  Optional[float] = None
    rationale:       Optional[str] = None
    days_to_confirm: Optional[int] = None

    def to_dict(self) -> Dict:
        return {
            "bonus_active":    self.bonus_active,
            "upgrade":         self.upgrade,
            "position_bonus":  self.position_bonus,
            "rationale":       self.rationale,
            "days_to_confirm": self.days_to_confirm,
        }


@dataclass
class RSIDirectionResult:
    """RSI direction signal (turning up from oversold is bullish)."""
    signal:      RSISignal
    label:       str
    rsi_current: float
    delta:       float
    pattern_bonus: int
    is_oversold:  bool
    is_overbought: bool

    def to_dict(self) -> Dict:
        return {
            "signal":        self.signal.value,
            "label":         self.label,
            "rsi_current":   self.rsi_current,
            "delta":         round(self.delta, 1),
            "pattern_bonus": self.pattern_bonus,
            "is_oversold":   self.is_oversold,
            "is_overbought": self.is_overbought,
        }


@dataclass
class PlaybookScenario:
    """Single if/then scenario in the conditional playbook."""
    scenario_id:    int
    name:           str
    condition_desc: str
    condition_met:  bool
    mode:           SignalMode
    action:         str
    details:        Dict[str, Any]
    conflict_score: str

    def to_dict(self) -> Dict:
        return {
            "scenario_id":    self.scenario_id,
            "name":           self.name,
            "condition_desc": self.condition_desc,
            "condition_met":  self.condition_met,
            "mode":           self.mode.value,
            "action":         self.action,
            "details":        self.details,
            "conflict_score": self.conflict_score,
        }


@dataclass
class FullEngineResult:
    """
    Complete output from the Thrive Alpha signal fusion engine.
    This is what gets returned to the UI layer.
    """
    ticker:           str
    timestamp:        str

    # Pre-flight
    classification:   ClassificationResult
    pre_flight_flags: List[PreFlightFlag]
    is_scoreable:     bool

    # Core outputs
    current_mode:            SignalMode
    current_action:          str
    position_size_multiplier: float

    # Analysis layers
    divergence:         Optional[DivergenceResult]
    blend:              Optional[BlendResult]
    regime_transition:  Optional[RegimeTransitionResult]
    coherence:          Optional[CoherenceResult]
    transition_bonus:   Optional[TransitionBonusResult]
    rsi_signal:         Optional[RSIDirectionResult]

    # Playbook
    playbook: List[PlaybookScenario]

    # Summary
    summary: Dict[str, Any]

    def to_dict(self) -> Dict:
        return {
            "ticker":     self.ticker,
            "timestamp":  self.timestamp,
            "classification":          self.classification.to_dict(),
            "is_scoreable":            self.is_scoreable,
            "current_mode":            self.current_mode.value,
            "current_action":          self.current_action,
            "position_size_multiplier": self.position_size_multiplier,
            "divergence":         self.divergence.to_dict() if self.divergence else None,
            "blend":              self.blend.to_dict() if self.blend else None,
            "regime_transition":  self.regime_transition.to_dict() if self.regime_transition else None,
            "coherence":          self.coherence.to_dict() if self.coherence else None,
            "transition_bonus":   self.transition_bonus.to_dict() if self.transition_bonus else None,
            "rsi_signal":         self.rsi_signal.to_dict() if self.rsi_signal else None,
            "playbook":           [s.to_dict() for s in self.playbook],
            "summary":            self.summary,
        }
