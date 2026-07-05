"""Stock split alignment for forward metrics."""
from signals.stock_splits import align_prices_across_split, cumulative_split_factor


def test_crwd_split_factor():
    assert cumulative_split_factor("CRWD", "2026-07-01", "2026-07-02") == 0.25
    assert cumulative_split_factor("CRWD", "2026-07-02", "2026-07-10") == 1.0
    assert cumulative_split_factor("SPY", "2026-07-01", "2026-07-02") == 1.0


def test_align_prices():
    start, end, sf = align_prices_across_split(
        "CRWD", "2026-07-01", "2026-07-02", 760.0, 196.8
    )
    assert sf == 0.25
    assert start == 190.0
    assert end == 196.8
