"""TL;DR key_level uses shared structural_invalidation_below."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from signals.structural_invalidation import structural_invalidation_below


def test_key_inv_prefers_ma200_over_deep_tail():
    ma200 = 60.0
    low_52w = 29.0
    stop_52w = round(low_52w * 0.97, 2)
    key_inv = structural_invalidation_below(ma200, low_52w, fallback=float(stop_52w))
    assert key_inv == ma200 * 0.97
    assert key_inv > stop_52w
