"""Bear dampening and index earnings-yield fair value."""
from __future__ import annotations

import sys
from pathlib import Path

# Running `python tests/test_*.py` does not load conftest — backend root must be on path.
# Prefer: `cd backend && python -m pytest tests/test_bear_and_index_fv.py -q`
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from signals.bear_dampening import apply_bear_dampening, BULL_BASELINE_ERROR_DEFAULT
from signals.fair_value_estimator import compute_index_fair_value


def test_apply_bear_dampening_long_term_noop():
    assert apply_bear_dampening(80.0, 80.0, 0.02, "long_term") == 80.0


def test_apply_bear_dampening_wide_band_and_hmm_bear():
    # error_band 3x baseline -> bear_ratio=3, need >3 and hmm>60 for dampening
    err = BULL_BASELINE_ERROR_DEFAULT * 4.0  # ratio 4
    out = apply_bear_dampening(80.0, 65.0, err, "swing")
    assert out < 80.0
    assert out >= 50.0


def test_apply_bear_dampening_no_trigger_low_hmm():
    err = BULL_BASELINE_ERROR_DEFAULT * 4.0
    assert apply_bear_dampening(80.0, 50.0, err, "swing") == 80.0


def test_compute_index_fair_value_spy_share_eps():
    # EPS ~27, rf 4.3%, ERP 4.5% -> required 8.8%, fair PE ~11.36
    fv = compute_index_fair_value(27.0, 0.043, 0.045, index_level_eps=False)
    assert 300 < fv < 320


def test_compute_index_fair_value_index_level_eps():
    fv = compute_index_fair_value(270.0, 0.043, 0.045, index_level_eps=True)
    assert 300 < fv < 320
