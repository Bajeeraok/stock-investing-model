"""
Thesis storage and nudges.
- Load/save thesis per ticker (why, exit_condition)
- Generate nudges when regime/score matches exit condition
"""
from __future__ import annotations

from pathlib import Path

import yaml


def load_theses(path: Path | None = None) -> dict[str, dict]:
    """Load theses: ticker -> {thesis, exit_condition, added_date}."""
    if path is None:
        path = Path(__file__).resolve().parent.parent / "data" / "theses.yaml"
    if not path.exists():
        return {}
    try:
        with open(path, "r") as f:
            data = yaml.safe_load(f) or {}
        return data.get("theses", {}) or {}
    except Exception:
        return {}


def save_thesis(ticker: str, thesis: str, exit_condition: str, path: Path | None = None) -> None:
    """Save thesis for ticker."""
    if path is None:
        path = Path(__file__).resolve().parent.parent / "data" / "theses.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    theses = load_theses(path)
    from datetime import datetime
    theses[ticker] = {
        "thesis": thesis,
        "exit_condition": exit_condition,
        "added_date": datetime.now().strftime("%Y-%m-%d"),
    }
    with open(path, "w") as f:
        yaml.safe_dump({"theses": theses}, f, default_flow_style=False)


def get_nudge(
    ticker: str,
    regime: str,
    score: float | None,
    theses: dict[str, dict],
) -> str | None:
    """
    Return nudge text when conditions match thesis exit_condition.
    - "Regime DOWN; you said trim if DOWN" when regime DOWN and exit mentions DOWN/trim
    - "Trend still strong; check thesis before selling" when score >= 65 and signal good
    """
    t = theses.get(ticker)
    if not t:
        return None
    exit_cond = (t.get("exit_condition") or "").lower()
    if not exit_cond:
        return None

    # Regime DOWN + exit says trim/DOWN
    if regime == "DOWN" and ("down" in exit_cond or "trim" in exit_cond):
        return "Regime DOWN; you said you'd trim. Review thesis."
    if regime == "DOWN" and "sell" in exit_cond and score is not None and score < 35:
        return "Regime DOWN, score low; you said you'd sell. Review thesis."

    # Score still strong - don't sell winner early
    if score is not None and score >= 65 and ("hold" in exit_cond or "trim" in exit_cond):
        return "Trend still strong; check thesis before selling."
    return None
