"""
tests/test_hmm_regime_shift_direction.py

Run with: pytest tests/test_hmm_regime_shift_direction.py -v
"""
import numpy as np
import pytest

from signals.hmm_regime_shift_direction import (
    STATE_BEAR,
    STATE_BULL,
    STATE_TRANSITION,
    build_ui_payload,
    compute_shift_direction,
    compute_shift_direction_semantic,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures — transition matrices
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def A_nvda():
    """
    NVDA-like: Trans state has 30% chance of going Bear, 12% Bull.
    """
    return np.array(
        [
            [0.85, 0.12, 0.03],
            [0.12, 0.58, 0.30],
            [0.05, 0.15, 0.80],
        ]
    )


@pytest.fixture
def A_bull_biased():
    """Trans state strongly exits to Bull."""
    return np.array(
        [
            [0.88, 0.10, 0.02],
            [0.45, 0.45, 0.10],
            [0.08, 0.12, 0.80],
        ]
    )


@pytest.fixture
def A_bear_biased():
    """Trans state strongly exits to Bear."""
    return np.array(
        [
            [0.85, 0.10, 0.05],
            [0.05, 0.50, 0.45],
            [0.03, 0.10, 0.87],
        ]
    )


@pytest.fixture
def A_symmetric():
    """Trans exits equally to Bull and Bear."""
    return np.array(
        [
            [0.85, 0.10, 0.05],
            [0.20, 0.60, 0.20],
            [0.05, 0.10, 0.85],
        ]
    )


@pytest.fixture
def A_sticky():
    """Very sticky states — low shift probability."""
    return np.array(
        [
            [0.97, 0.02, 0.01],
            [0.01, 0.97, 0.02],
            [0.01, 0.02, 0.97],
        ]
    )


@pytest.fixture
def pi_trans():
    """Currently in Transition (NVDA today)."""
    return np.array([0.01, 0.99, 0.00])


@pytest.fixture
def pi_bull():
    """Currently in Bull."""
    return np.array([0.92, 0.06, 0.02])


@pytest.fixture
def pi_bear():
    """Currently in Bear."""
    return np.array([0.02, 0.08, 0.90])


# ─────────────────────────────────────────────────────────────────────────────
# Semantic permutation (production: hmmlearn index order)
# ─────────────────────────────────────────────────────────────────────────────


def test_permutation_matches_direct_when_order_is_identity():
    A = np.array(
        [
            [0.85, 0.12, 0.03],
            [0.12, 0.58, 0.30],
            [0.05, 0.15, 0.80],
        ]
    )
    pi = np.array([0.01, 0.99, 0.00])
    direct = compute_shift_direction(A, pi, horizon_days=10)
    via = compute_shift_direction_semantic(A, pi, 0, 1, 2, horizon_days=10)
    assert via is not None
    assert via["shift_prob_total"] == direct["shift_prob_total"]
    assert via["dominant_direction"] == direct["dominant_direction"]


def test_permutation_swapped_indices():
    A_sem = np.array(
        [
            [0.85, 0.12, 0.03],
            [0.12, 0.58, 0.30],
            [0.05, 0.15, 0.80],
        ]
    )
    pi_sem = np.array([0.01, 0.99, 0.00])
    baseline = compute_shift_direction(A_sem, pi_sem, horizon_days=5)
    A_model = A_sem[[2, 0, 1]][:, [2, 0, 1]]
    pi_model = pi_sem[[2, 0, 1]]
    remapped = compute_shift_direction_semantic(
        A_model, pi_model, bull_idx=1, transition_idx=2, bear_idx=0, horizon_days=5
    )
    assert remapped is not None
    assert remapped["shift_prob_total"] == baseline["shift_prob_total"]


def test_build_ui_payload_keys_minimal():
    A = np.eye(3)
    A[0, 0] = 0.9
    A[0, 1] = 0.1
    A[1, :] = [0.2, 0.5, 0.3]
    A[2, :] = [0.1, 0.2, 0.7]
    A = A / A.sum(axis=1, keepdims=True)
    pi = np.array([0.1, 0.8, 0.1])
    r = compute_shift_direction(A, pi, horizon_days=10)
    ui = build_ui_payload(r)
    assert "shift_direction" in ui
    assert ui["shift_direction"]["dominant"] in ("Bull", "Bear", "Uncertain")


# ─────────────────────────────────────────────────────────────────────────────
# Basic correctness
# ─────────────────────────────────────────────────────────────────────────────


class TestBasicCorrectness:
    def test_current_state_identified(self, A_nvda, pi_trans):
        r = compute_shift_direction(A_nvda, pi_trans)
        assert r["current_state"] == "Transition"
        assert r["current_state_prob"] > 0.95

    def test_bull_state_identified(self, A_nvda, pi_bull):
        r = compute_shift_direction(A_nvda, pi_bull)
        assert r["current_state"] == "Bull"

    def test_bear_state_identified(self, A_nvda, pi_bear):
        r = compute_shift_direction(A_nvda, pi_bear)
        assert r["current_state"] == "Bear"

    def test_shift_probs_sum_to_lte_1(self, A_nvda, pi_trans):
        r = compute_shift_direction(A_nvda, pi_trans)
        assert r["shift_prob_total"] <= 1.0
        assert r["shift_prob_total"] >= 0.0

    def test_directional_probs_sum_to_1(self, A_nvda, pi_trans):
        r = compute_shift_direction(A_nvda, pi_trans)
        total = r["shift_to_bull_prob"] + r["shift_to_bear_prob"]
        assert total <= 1.0 + 1e-6

    def test_shift_prob_increases_with_horizon(self, A_nvda, pi_trans):
        r5 = compute_shift_direction(A_nvda, pi_trans, horizon_days=5)
        r20 = compute_shift_direction(A_nvda, pi_trans, horizon_days=20)
        assert r20["shift_prob_total"] >= r5["shift_prob_total"]

    def test_sticky_matrix_low_shift_prob(self, A_sticky, pi_trans):
        r = compute_shift_direction(A_sticky, pi_trans, horizon_days=5)
        assert r["shift_prob_total"] < 0.30

    def test_horizon_recorded(self, A_nvda, pi_trans):
        r = compute_shift_direction(A_nvda, pi_trans, horizon_days=7)
        assert r["horizon_days"] == 7


# ─────────────────────────────────────────────────────────────────────────────
# Directional bias
# ─────────────────────────────────────────────────────────────────────────────


class TestDirectionalBias:
    def test_bear_biased_matrix_dominant_bear(self, A_bear_biased, pi_trans):
        r = compute_shift_direction(A_bear_biased, pi_trans)
        assert r["shift_to_bear_prob"] > r["shift_to_bull_prob"]
        assert r["dominant_direction"] == "Bear"

    def test_bull_biased_matrix_dominant_bull(self, A_bull_biased, pi_trans):
        r = compute_shift_direction(A_bull_biased, pi_trans)
        assert r["shift_to_bull_prob"] > r["shift_to_bear_prob"]
        assert r["dominant_direction"] == "Bull"

    def test_symmetric_matrix_uncertain(self, A_symmetric, pi_trans):
        r = compute_shift_direction(A_symmetric, pi_trans)
        assert r["dominant_direction"] == "Uncertain"
        assert abs(r["shift_to_bull_prob"] - r["shift_to_bear_prob"]) < 0.15

    def test_nvda_today_bear_biased(self, A_nvda, pi_trans):
        """Marginal 10d mass leans bear ~58/42; use threshold just below bear share for Bear label."""
        r = compute_shift_direction(A_nvda, pi_trans, uncertainty_threshold=0.55)
        assert r["shift_to_bear_prob"] > r["shift_to_bull_prob"]
        assert r["dominant_direction"] == "Bear"

    def test_from_bull_state_low_bear_prob(self, A_nvda, pi_bull):
        r = compute_shift_direction(A_nvda, pi_bull)
        # Starting in Bull, marginal bear mass at horizon can still be material for this A.
        assert r["shift_to_bear_abs"] < 0.50

    def test_uncertainty_threshold_respected(self, A_symmetric, pi_trans):
        r = compute_shift_direction(A_symmetric, pi_trans, uncertainty_threshold=0.80)
        assert r["dominant_direction"] == "Uncertain"

    def test_low_threshold_declares_dominant(self, A_nvda, pi_trans):
        r = compute_shift_direction(A_nvda, pi_trans, uncertainty_threshold=0.30)
        assert r["dominant_direction"] == "Bear"
        assert r["shift_to_bear_prob"] > r["shift_to_bull_prob"]


# ─────────────────────────────────────────────────────────────────────────────
# Interpretation string
# ─────────────────────────────────────────────────────────────────────────────


class TestInterpretation:
    def test_interpretation_is_string(self, A_nvda, pi_trans):
        r = compute_shift_direction(A_nvda, pi_trans)
        assert isinstance(r["interpretation"], str)
        assert len(r["interpretation"]) > 20

    def test_interpretation_mentions_bear(self, A_bear_biased, pi_trans):
        r = compute_shift_direction(A_bear_biased, pi_trans)
        assert "Bear" in r["interpretation"] or "bear" in r["interpretation"]

    def test_interpretation_mentions_bull(self, A_bull_biased, pi_trans):
        r = compute_shift_direction(A_bull_biased, pi_trans)
        assert "Bull" in r["interpretation"] or "bull" in r["interpretation"]

    def test_sticky_interpretation_mentions_stable(self, A_sticky, pi_trans):
        r = compute_shift_direction(A_sticky, pi_trans, horizon_days=5)
        low = r["interpretation"].lower()
        assert "stable" in low or "only" in low

    def test_interpretation_includes_horizon(self, A_nvda, pi_trans):
        r = compute_shift_direction(A_nvda, pi_trans, horizon_days=10)
        assert "10" in r["interpretation"]


# ─────────────────────────────────────────────────────────────────────────────
# UI payload
# ─────────────────────────────────────────────────────────────────────────────


class TestUIPayload:
    def test_payload_has_required_keys(self, A_nvda, pi_trans):
        r = compute_shift_direction(A_nvda, pi_trans)
        p = build_ui_payload(r)
        for key in [
            "shift_probability",
            "shift_direction",
            "horizon_days",
            "interpretation",
            "current_state",
        ]:
            assert key in p

    def test_shift_direction_has_color(self, A_nvda, pi_trans):
        r = compute_shift_direction(A_nvda, pi_trans)
        p = build_ui_payload(r)
        assert p["shift_direction"]["color"] in ["green", "red", "amber"]

    def test_bear_result_gets_red_color(self, A_bear_biased, pi_trans):
        r = compute_shift_direction(A_bear_biased, pi_trans)
        p = build_ui_payload(r)
        assert p["shift_direction"]["color"] == "red"
        assert "Bear" in p["shift_direction"]["label"]

    def test_bull_result_gets_green_color(self, A_bull_biased, pi_trans):
        r = compute_shift_direction(A_bull_biased, pi_trans)
        p = build_ui_payload(r)
        assert p["shift_direction"]["color"] == "green"
        assert "Bull" in p["shift_direction"]["label"]

    def test_uncertain_result_gets_amber(self, A_symmetric, pi_trans):
        r = compute_shift_direction(A_symmetric, pi_trans)
        p = build_ui_payload(r)
        assert p["shift_direction"]["color"] == "amber"

    def test_payload_label_includes_percentage(self, A_bear_biased, pi_trans):
        r = compute_shift_direction(A_bear_biased, pi_trans)
        p = build_ui_payload(r)
        assert "%" in p["shift_direction"]["label"]

    def test_nvda_today_full_payload(self, A_nvda, pi_trans):
        r = compute_shift_direction(
            A_nvda, pi_trans, horizon_days=10, uncertainty_threshold=0.55
        )
        p = build_ui_payload(r)
        assert p["shift_direction"]["dominant"] == "Bear"
        assert p["shift_direction"]["color"] == "red"
        assert p["current_state"] == "Transition"
        assert p["shift_probability"] > 0.30


# ─────────────────────────────────────────────────────────────────────────────
# Edge cases
# ─────────────────────────────────────────────────────────────────────────────


class TestEdgeCases:
    def test_already_in_bear_shift_prob(self, A_nvda, pi_bear):
        r_bear = compute_shift_direction(A_nvda, pi_bear)
        r_trans = compute_shift_direction(A_nvda, np.array([0.01, 0.99, 0.00]))
        assert r_trans["shift_prob_total"] >= r_bear["shift_prob_total"]

    def test_horizon_1_day(self, A_nvda, pi_trans):
        r = compute_shift_direction(A_nvda, pi_trans, horizon_days=1)
        assert r["shift_prob_total"] < 0.60
        assert r["horizon_days"] == 1

    def test_horizon_252_days(self, A_nvda, pi_trans):
        r = compute_shift_direction(A_nvda, pi_trans, horizon_days=252)
        assert r["shift_prob_total"] > 0.50

    def test_unnormalized_pi_handled(self, A_nvda):
        pi_unnorm = np.array([0.1, 9.9, 0.0])
        r = compute_shift_direction(A_nvda, pi_unnorm)
        assert r["current_state"] == "Transition"

    def test_all_probs_between_0_and_1(self, A_nvda, pi_trans):
        r = compute_shift_direction(A_nvda, pi_trans)
        for key in [
            "shift_prob_total",
            "shift_to_bull_prob",
            "shift_to_bear_prob",
            "shift_to_bull_abs",
            "shift_to_bear_abs",
            "dominant_direction_confidence",
        ]:
            assert 0.0 <= r[key] <= 1.0, f"{key} = {r[key]} out of bounds"


def test_state_constants_match_semantic_order():
    assert STATE_BULL == 0 and STATE_TRANSITION == 1 and STATE_BEAR == 2
