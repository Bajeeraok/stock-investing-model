"""
Known stock splits for aligning EOD snapshot closes across corporate actions.

EOD snapshots store closes as-of fetch time (not retro-adjusted). When a forward
pair spans a split, divide pre-split prices by `ratio` (4-for-1 → ratio=4).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from typing import Any

# Built-in registry (config `stock_splits` can extend/override per ticker).
_BUILTIN: dict[str, tuple[tuple[str, float], ...]] = {
    "CRWD": (("2026-07-02", 4.0),),  # 4-for-1; split-adjusted trading from Jul 2, 2026
}


@dataclass(frozen=True)
class StockSplit:
    effective_date: date
    ratio: float  # 4-for-1 → 4.0 (price ÷ ratio)


def _parse_date(date_str: str | None) -> date | None:
    if not date_str:
        return None
    try:
        return date.fromisoformat(str(date_str)[:10])
    except ValueError:
        return None


def _norm_ticker(ticker: str | None) -> str:
    return (ticker or "").upper().split("-")[0].strip()


def _parse_split_entry(raw: Any) -> StockSplit | None:
    if not isinstance(raw, dict):
        return None
    eff = _parse_date(raw.get("effective_date"))
    try:
        ratio = float(raw.get("ratio"))
    except (TypeError, ValueError):
        return None
    if eff is None or ratio <= 1.0:
        return None
    return StockSplit(effective_date=eff, ratio=ratio)


@lru_cache(maxsize=1)
def _config_splits_raw() -> dict[str, tuple[tuple[str, float], ...]]:
    try:
        from config_loader import load_config

        cfg = load_config() or {}
        block = cfg.get("stock_splits") or {}
        if not isinstance(block, dict):
            return {}
        out: dict[str, tuple[tuple[str, float], ...]] = {}
        for sym, entries in block.items():
            if not isinstance(entries, list):
                continue
            parsed: list[tuple[str, float]] = []
            for e in entries:
                sp = _parse_split_entry(e)
                if sp:
                    parsed.append((sp.effective_date.isoformat(), sp.ratio))
            if parsed:
                out[_norm_ticker(str(sym))] = tuple(
                    sorted(parsed, key=lambda x: x[0])
                )
        return out
    except Exception:
        return {}


def splits_for_ticker(ticker: str | None) -> list[StockSplit]:
    sym = _norm_ticker(ticker)
    if not sym:
        return []
    merged: dict[str, float] = {}
    for eff, ratio in _BUILTIN.get(sym, ()):
        merged[eff] = ratio
    for eff, ratio in _config_splits_raw().get(sym, ()):
        merged[eff] = ratio
    return [
        StockSplit(effective_date=date.fromisoformat(eff), ratio=ratio)
        for eff, ratio in sorted(merged.items())
    ]


def cumulative_split_factor(
    ticker: str | None,
    from_date: str | None,
    to_date: str | None,
) -> float:
    """
    Multiply a price at `from_date` by this factor to express it on `to_date`'s share basis.

    Example: CRWD 4-for-1 with from=2026-07-01, to=2026-07-02 → 0.25 (price ÷ 4).
    """
    d0 = str(from_date or "")[:10]
    d1 = str(to_date or "")[:10]
    if not d0 or not d1 or d0 >= d1:
        return 1.0
    factor = 1.0
    for sp in splits_for_ticker(ticker):
        eff = sp.effective_date.isoformat()
        if d0 < eff <= d1:
            factor /= sp.ratio
    return factor


def align_prices_across_split(
    ticker: str | None,
    start_date: str | None,
    end_date: str | None,
    start_price: float | None,
    end_price: float | None,
) -> tuple[float | None, float | None, float]:
    """Return (adj_start, end_price, split_factor). Only start is scaled when crossing a split."""
    if start_price is None:
        return None, end_price, 1.0
    sf = cumulative_split_factor(ticker, start_date, end_date)
    if sf == 1.0:
        return start_price, end_price, 1.0
    return round(start_price * sf, 6), end_price, sf
