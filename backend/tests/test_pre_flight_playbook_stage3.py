"""Stage 3 conditional playbook: strict AND includes pattern score (see Thresholds.PATTERN_STAGE3_REGIME_SHIFT)."""

from signals.pre_flight import classify_asset
from signals.pre_flight.models import SignalInput
from signals.pre_flight.signal_fusion import run_conditional_playbook


def _pb(s: SignalInput):
    return run_conditional_playbook(s, classify_asset(s.ticker))


def test_stage3_not_met_when_pattern_below_threshold():
    """NVDA-like: transition high but pattern 38 — scenario 3 must not show condition_met."""
    s = SignalInput(
        ticker="NVDA",
        hmm_bull_prob=1.0,
        hmm_transition_prob=99.0,
        hmm_bear_prob=0.0,
        pattern_score=38.0,
        ml_probability=10.0,
        options_sentiment=50.0,
    )
    _, _, _, playbook = _pb(s)
    sc3 = next(x for x in playbook if x.scenario_id == 3)
    assert sc3.condition_met is False


def test_stage3_met_when_pattern_above_threshold():
    s = SignalInput(
        ticker="NVDA",
        hmm_bull_prob=1.0,
        hmm_transition_prob=99.0,
        hmm_bear_prob=0.0,
        pattern_score=55.0,
        ml_probability=10.0,
        options_sentiment=50.0,
    )
    _, _, _, playbook = _pb(s)
    sc3 = next(x for x in playbook if x.scenario_id == 3)
    assert sc3.condition_met is True
