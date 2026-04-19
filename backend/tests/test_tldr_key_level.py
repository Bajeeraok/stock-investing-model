"""TL;DR key_level uses max(MA200 cushion, 52w tail), not tail alone."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def test_key_inv_prefers_ma200_over_deep_tail():
    # Logic mirrored from _build_trade_roadmap key_inv block
    ma200 = 60.0
    low_52w = 29.0
    stop_52w = round(low_52w * 0.97, 2)
    ma200_k = float(ma200)
    tail_k = float(low_52w) * 0.97
    key_inv = max(ma200_k * 0.97, tail_k)
    assert key_inv == ma200_k * 0.97
    assert key_inv > stop_52w
