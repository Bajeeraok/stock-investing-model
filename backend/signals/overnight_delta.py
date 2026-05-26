"""
Overnight delta — what changed since last dashboard baseline.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_BASELINE_NAME = "overnight_baseline.json"


def _baseline_path(data_root: Path) -> Path:
    return data_root / _BASELINE_NAME


def save_overnight_baseline(data_root: Path, snapshot: dict[str, Any]) -> None:
    try:
        data_root.mkdir(parents=True, exist_ok=True)
        _baseline_path(data_root).write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    except Exception as e:
        logger.debug("save_overnight_baseline: %s", e)


def _delta_line(label: str, prev: float | None, curr: float | None, *, pct: bool = False, invert_good: bool = False) -> dict[str, Any] | None:
    if prev is None or curr is None:
        return None
    try:
        p, c = float(prev), float(curr)
    except (TypeError, ValueError):
        return None
    d = c - p
    if abs(d) < (0.01 if not pct else 0.05):
        return None
    good = d > 0 if not invert_good else d < 0
    if pct:
        text = f"{label}: {p:.2f}% → {c:.2f}% ({d:+.2f}%)"
    else:
        text = f"{label}: {p:.2f} → {c:.2f} ({d:+.2f})"
    return {"label": label, "text": text, "direction": "up" if d > 0 else "down", "good_for_stocks": good}


def build_overnight_delta(
    *,
    data_root: Path | None,
    cross_asset: list[dict] | None,
    macro_regime_bundle: dict | None,
    premarket: dict | None = None,
) -> dict[str, Any] | None:
    if not data_root:
        return None
    path = _baseline_path(data_root)
    if not path.exists():
        return None

    try:
        baseline = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None

    factors = (macro_regime_bundle or {}).get("factors") or {}
    curr = {
        "vix": factors.get("vix"),
        "hy_oas_bp": factors.get("hy_oas_bp"),
        "yield_10y": factors.get("dgs10") or factors.get("yield_10y"),
    }
    for row in cross_asset or []:
        if not isinstance(row, dict):
            continue
        lbl = (row.get("label") or row.get("ticker") or "").upper()
        ch = row.get("change_pct")
        if lbl in ("USO", "CRUDE", "OIL") and ch is not None:
            curr["oil_pct"] = ch
        if lbl in ("UUP", "DXY", "DOLLAR") and ch is not None:
            curr["dxy_pct"] = ch

    lines: list[dict[str, Any]] = []
    for key, label, inv in (
        ("vix", "VIX", True),
        ("yield_10y", "10yr yield", True),
        ("hy_oas_bp", "HY spread (bp)", True),
    ):
        row = _delta_line(label, baseline.get(key), curr.get(key), invert_good=inv)
        if row:
            lines.append(row)
    for key, label in (("oil_pct", "Oil"), ("dxy_pct", "Dollar")):
        row = _delta_line(label, baseline.get(key), curr.get(key), pct=True)
        if row:
            lines.append(row)

    if not lines:
        return None

    good = sum(1 for x in lines if x.get("good_for_stocks"))
    bad = len(lines) - good
    if good > bad:
        summary = "Overnight lean modestly positive for risk assets — rates/fear cooling."
    elif bad > good:
        summary = "Overnight lean cautious — yields up or fear rising."
    else:
        summary = "Overnight mixed — tape will decide at the open."

    es = (premarket or {}).get("es_pct")
    if es is not None:
        summary += f" ES pre-market {es:+.2f}%."

    return {"lines": lines[:6], "summary": summary}


def snapshot_for_baseline(
    cross_asset: list[dict] | None,
    macro_regime_bundle: dict | None,
) -> dict[str, Any]:
    factors = (macro_regime_bundle or {}).get("factors") or {}
    out: dict[str, Any] = {
        "vix": factors.get("vix"),
        "hy_oas_bp": factors.get("hy_oas_bp"),
        "yield_10y": factors.get("dgs10") or factors.get("yield_10y"),
    }
    for row in cross_asset or []:
        if not isinstance(row, dict):
            continue
        lbl = (row.get("label") or row.get("ticker") or "").upper()
        ch = row.get("change_pct")
        if lbl in ("USO", "CRUDE", "OIL") and ch is not None:
            out["oil_pct"] = ch
        if lbl in ("UUP", "DXY", "DOLLAR") and ch is not None:
            out["dxy_pct"] = ch
    return out
