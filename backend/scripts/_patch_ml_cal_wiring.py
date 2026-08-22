"""Patch wiring for ML calibration factor."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def patch_actionable() -> None:
    p = ROOT / "signals" / "actionable_score.py"
    text = p.read_text(encoding="utf-8")
    sig_old = (
        "def attach_actionable_score(\n"
        "    investor_out: dict[str, Any],\n"
        "    *,\n"
        "    price_age_hours: float | None = None,\n"
        "    ml_calibration_factor: float | None = None,\n"
        ") -> dict[str, Any]:"
    )
    sig_new = (
        "def attach_actionable_score(\n"
        "    investor_out: dict[str, Any],\n"
        "    *,\n"
        "    price_age_hours: float | None = None,\n"
        "    ml_calibration_factor: float | None = None,\n"
        "    config: dict[str, Any] | None = None,\n"
        ") -> dict[str, Any]:"
    )
    if sig_old not in text:
        raise SystemExit("actionable sig not found")
    text = text.replace(sig_old, sig_new)

    old = (
        "    block = compute_actionable_score(\n"
        '        investor_out.get("pattern_score"),\n'
        "        gates_passed=int(passed) if passed is not None else None,\n"
        "        gates_total=int(total) if total is not None else 4,\n"
        "        fused_confidence_pct=_sf(conf),\n"
        "        price_age_hours=price_age_hours,\n"
        "        ml_calibration_factor=ml_calibration_factor,\n"
        "    )\n"
        '    investor_out["actionable_score"] = block\n'
        "    return investor_out\n"
    )
    new = (
        "    cal = ml_calibration_factor\n"
        "    if cal is None:\n"
        "        try:\n"
        "            from signals.ml_calibration_store import get_ml_calibration_factor\n"
        "\n"
        "            cal = get_ml_calibration_factor(config)\n"
        "        except Exception:\n"
        "            cal = 1.0\n"
        "\n"
        "    block = compute_actionable_score(\n"
        '        investor_out.get("pattern_score"),\n'
        "        gates_passed=int(passed) if passed is not None else None,\n"
        "        gates_total=int(total) if total is not None else 4,\n"
        "        fused_confidence_pct=_sf(conf),\n"
        "        price_age_hours=price_age_hours,\n"
        "        ml_calibration_factor=cal,\n"
        "    )\n"
        '    investor_out["actionable_score"] = block\n'
        "    return investor_out\n"
    )
    if old not in text:
        raise SystemExit("actionable block not found")
    p.write_text(text.replace(old, new), encoding="utf-8")
    print("patched actionable_score")


def patch_config() -> None:
    p = ROOT / "config" / "config.yaml"
    text = p.read_text(encoding="utf-8")
    old = (
        "  calibration:\n"
        "    enabled: false                        # set true after running scripts/fit_probability_calibration.py\n"
        "    path: data/calibration/ml_horizons.json  # relative to backend/\n"
    )
    new = (
        "  calibration:\n"
        "    # Platt map for displayed ML horizon probs + actionable_score discount.\n"
        "    # Fit: python scripts/_run_fit_ml_cal.py\n"
        "    enabled: true\n"
        "    actionable_factor_enabled: true\n"
        "    path: data/calibration/ml_horizons.json  # relative to backend/\n"
    )
    if old not in text:
        m = re.search(r"  calibration:\n(?:    .*\n){1,6}", text)
        raise SystemExit(f"config block not found; nearby={m.group(0)!r if m else None}")
    p.write_text(text.replace(old, new), encoding="utf-8")
    print("patched config.yaml")


def patch_tests() -> None:
    p = ROOT / "tests" / "test_actionable_score.py"
    text = p.read_text(encoding="utf-8")
    text = text.replace(
        "    attach_actionable_score(inv)\n",
        "    attach_actionable_score(inv, ml_calibration_factor=1.0)\n",
    )
    if "test_ml_calibration_factor_discounts_actionable" not in text:
        text += """

def test_ml_calibration_factor_discounts_actionable():
    raw = compute_actionable_score(
        80.0,
        gates_passed=4,
        gates_total=4,
        fused_confidence_pct=70.0,
        ml_calibration_factor=1.0,
    )
    discounted = compute_actionable_score(
        80.0,
        gates_passed=4,
        gates_total=4,
        fused_confidence_pct=70.0,
        ml_calibration_factor=0.75,
    )
    assert raw["actionable"] == 80.0
    assert discounted["actionable"] == 60.0
    assert discounted["factors"]["ml_calibration_factor"] == 0.75
"""
    p.write_text(text, encoding="utf-8")
    print("patched tests")


def patch_csv() -> None:
    p = ROOT / "signals" / "signal_audit_report.py"
    text = p.read_text(encoding="utf-8")
    if '("ml_short_prob", "ml_short_prob")' in text:
        print("csv already has ml_short_prob")
        return
    needle = '    ("ml_signal", "ml_signal"),\n    ("confidence_low", "confidence_low"),'
    repl = (
        '    ("ml_signal", "ml_signal"),\n'
        '    ("ml_short_prob", "ml_short_prob"),\n'
        '    ("confidence_low", "confidence_low"),'
    )
    if needle not in text:
        raise SystemExit("csv needle not found")
    p.write_text(text.replace(needle, repl, 1), encoding="utf-8")
    print("patched csv columns")


def patch_store_respect_flag() -> None:
    p = ROOT / "signals" / "ml_calibration_store.py"
    text = p.read_text(encoding="utf-8")
    # ensure actionable_factor_enabled is honored (already is)
    if "actionable_factor_enabled" not in text:
        raise SystemExit("store missing actionable_factor_enabled")
    print("store ok")


if __name__ == "__main__":
    patch_actionable()
    patch_config()
    patch_tests()
    patch_csv()
    patch_store_respect_flag()
    print("done")
