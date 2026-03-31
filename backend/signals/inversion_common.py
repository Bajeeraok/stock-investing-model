"""
Shared inversion detection for backtests and diagnostics.

Use this instead of reimplementing bucket comparisons in multiple modules.
"""

from __future__ import annotations

from typing import Any

from signals.signal_inversion import BucketStats, detect_inversion


def bucket_stats_from_rows(rows: list[dict[str, Any]]) -> list[BucketStats]:
    """
    Build BucketStats from dicts with keys: bucket, mean_return, hit_rate (optional), n.
    """
    out: list[BucketStats] = []
    for r in rows:
        out.append(
            BucketStats(
                bucket=str(r.get("bucket") or ""),
                mean_return=float(r.get("mean_return", 0.0)),
                hit_rate=float(r.get("hit_rate", 0.0)),
                n=int(r.get("n", 0)),
            )
        )
    return out


def detect_inversion_from_bucket_rows(
    rows: list[dict[str, Any]],
    *,
    horizon: str = "3m",
    min_n: int = 20,
) -> dict[str, Any]:
    """Delegate to signal_inversion.detect_inversion with parsed BucketStats."""
    return detect_inversion(bucket_stats_from_rows(rows), horizon=horizon, min_n=min_n)
