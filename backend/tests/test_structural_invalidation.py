import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from signals.structural_invalidation import structural_invalidation_below


def test_prefers_ma200_over_deep_tail():
    assert structural_invalidation_below(60.0, 29.0, fallback=28.0) == 60.0 * 0.97


def test_fallback_when_no_ma200():
    assert structural_invalidation_below(None, 100.0, fallback=97.0) == 100.0 * 0.97


def test_ma200_only():
    assert structural_invalidation_below(50.0, None, fallback=40.0) == 50.0 * 0.97
