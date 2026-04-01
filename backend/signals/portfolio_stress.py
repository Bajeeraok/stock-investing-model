"""
Illustrative portfolio stress scenarios (parallel shocks) and per-signal uncertainty hints.
"""
from __future__ import annotations

from typing import Any


def enrich_signal_uncertainty(row: dict[str, Any]) -> None:
    """
    Add row['uncertainty'] from existing bands/ATR. Mutates row in place.
    """
    close = row.get("close")
    st = row.get("st_band")
    atr = row.get("atr_14")
    out: dict[str, Any] = {}

    try:
        c = float(close) if close is not None else None
    except (TypeError, ValueError):
        c = None

    if c and isinstance(st, dict) and st.get("low") is not None and st.get("high") is not None:
        try:
            lo, hi = float(st["low"]), float(st["high"])
            w = hi - lo
            if c > 0:
                out["st_band_width_pct"] = round(100.0 * w / c, 1)
        except (TypeError, ValueError):
            pass

    if c and atr is not None:
        try:
            a = float(atr)
            if c > 0:
                atr_pct = 100.0 * a / c
                out["atr_pct_of_price"] = round(atr_pct, 2)
                out["typical_range_label"] = f"~±{round(atr_pct * 1.5, 1)}% (1.5×ATR vs spot)"
        except (TypeError, ValueError):
            pass

    row["uncertainty"] = out if out else {}


def build_portfolio_stress_scenarios(
    report: dict[str, Any],
    *,
    shocks: list[tuple[str, float]] | None = None,
) -> dict[str, Any]:
    """
    Parallel shock to total portfolio value (β≈1 illustration). Not a factor model.
    """
    total = float(report.get("total_value") or 0.0)
    if total <= 0:
        return {
            "base_value": 0.0,
            "scenarios": [],
            "disclaimer": "Add holdings with prices to see stress scenarios.",
        }

    if shocks is None:
        shocks = [
            ("Broad market −10%", -0.10),
            ("Broad market −20%", -0.20),
            ("Broad market −30%", -0.30),
        ]

    scenarios: list[dict[str, Any]] = []
    for name, shock in shocks:
        after = total * (1.0 + shock)
        scenarios.append(
            {
                "name": name,
                "shock_pct": round(shock * 100.0, 1),
                "portfolio_value_after": round(after, 2),
                "loss_dollars": round(after - total, 2),
            }
        )

    return {
        "base_value": round(total, 2),
        "scenarios": scenarios,
        "disclaimer": (
            "Illustrative: assumes all holdings move together with the shock (β≈1). "
            "Real outcomes depend on betas, USD, dividends, and correlations."
        ),
    }
