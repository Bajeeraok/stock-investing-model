"""Shared inversion wrapper."""

from __future__ import annotations

from signals.inversion_common import detect_inversion_from_bucket_rows


def test_detect_inversion_from_bucket_rows():
    rows = [
        {"bucket": "strong", "mean_return": -5.0, "n": 25},
        {"bucket": "weak", "mean_return": 15.0, "n": 25},
    ]
    out = detect_inversion_from_bucket_rows(rows, min_n=10)
    assert out.get("inverted") is True
