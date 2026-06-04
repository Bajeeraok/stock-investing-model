"""
Forward-tracking summaries grouped by retail trading lens (Scout / Swing / Owner).
Uses existing EOD-paired horizon stats — no new data vendors.
"""
from __future__ import annotations

from typing import Any

LENS_HORIZONS: dict[str, list[int]] = {
    "scout": [1, 5, 20],
    "swing": [20, 60],
    "owner": [60],
}

LENS_PRIMARY_HORIZON: dict[str, int] = {
    "scout": 5,
    "swing": 20,
    "owner": 60,
}


def _horizon_stats(summary_by_horizon: dict[Any, Any], horizon: int) -> dict[str, Any] | None:
    for key in (horizon, str(horizon)):
        row = summary_by_horizon.get(key)
        if isinstance(row, dict) and row.get("n_observations"):
            return row
    return None


def build_summary_by_lens(forward_tracking: dict[str, Any] | None) -> dict[str, Any]:
    """
    Build per-lens hit-rate lines from summary_by_horizon + summary_by_signal (20d ADD bucket).
    """
    if not forward_tracking or not isinstance(forward_tracking, dict):
        return {}

    by_horizon = forward_tracking.get("summary_by_horizon") or {}
    by_signal = forward_tracking.get("summary_by_signal") or {}
    add_stats = by_signal.get("HOLD/ADD") or by_signal.get("ADD") or {}

    out: dict[str, Any] = {}
    for lens, horizons in LENS_HORIZONS.items():
        primary_h = LENS_PRIMARY_HORIZON[lens]
        primary = _horizon_stats(by_horizon, primary_h)
        horizon_rows = []
        for h in horizons:
            row = _horizon_stats(by_horizon, h)
            if row:
                horizon_rows.append(
                    {
                        "horizon_days": h,
                        "win_rate_pct": row.get("win_rate_pct"),
                        "avg_return_pct": row.get("avg_return_pct"),
                        "n_observations": row.get("n_observations"),
                        "st_target_hit_rate_pct": row.get("st_target_hit_rate_pct"),
                    }
                )

        add_hit = add_stats.get("hit_rate_pct")
        add_n = add_stats.get("n_observations")
        label_parts: list[str] = []
        if primary:
            wr = primary.get("win_rate_pct")
            n = primary.get("n_observations")
            if wr is not None and n:
                label_parts.append(f"{primary_h}d win {wr:.0f}% (n={n})")
        if add_hit is not None and add_n and lens in ("swing", "owner"):
            label_parts.append(f"ADD 20d {add_hit:.0f}% (n={add_n})")

        out[lens] = {
            "primary_horizon_days": primary_h,
            "primary": primary,
            "horizons": horizon_rows,
            "add_20d": {
                "hit_rate_pct": add_hit,
                "n_observations": add_n,
                "avg_return_pct": add_stats.get("avg_return_pct") or add_stats.get("avg_return_20d_pct"),
            }
            if add_stats
            else None,
            "label": " · ".join(label_parts) if label_parts else None,
        }
    return out
