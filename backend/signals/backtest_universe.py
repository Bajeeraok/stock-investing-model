"""
DIY backtest universe rules — honesty without a constituents subscription.

- full_history: keep only tickers with enough adjusted OHLCV bars for the period (reduces
  obvious survivorship from tickers with no history yet; does NOT replace index membership).
- membership_csv: you maintain (ticker, start_date, end_date) rows; filters which symbols
  are eligible at the backtest start date (v1); point-in-time per-bar filtering can extend later.

See config backtest.universe.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


def _tbase(sym: str) -> str:
    return str(sym).upper().replace(".", "-").split("-")[0]


def _resolve_csv_path(raw: str | None, backend_root: Path) -> Path | None:
    if not raw or not str(raw).strip():
        return None
    p = Path(raw.strip())
    if p.is_absolute():
        return p
    return (backend_root / p).resolve()


def load_membership_ranges_csv(path: Path) -> pd.DataFrame:
    """
    CSV columns (header required):
      ticker, start_date, end_date

    end_date may be empty for still-active names. Dates are parsed as UTC-naive dates.
    """
    df = pd.read_csv(path)
    cols = {c.lower().strip(): c for c in df.columns}
    for req in ("ticker", "start_date"):
        if req not in cols:
            raise ValueError(f"membership CSV missing column {req!r}: {path}")
    tcol = cols["ticker"]
    scol = cols["start_date"]
    ecol = cols.get("end_date")
    out = pd.DataFrame(
        {
            "ticker": df[tcol].astype(str).str.upper().str.strip(),
            "start_date": pd.to_datetime(df[scol], utc=False).dt.normalize(),
        }
    )
    if ecol:
        end = pd.to_datetime(df[ecol], utc=False, errors="coerce").dt.normalize()
        out["end_date"] = end
    else:
        out["end_date"] = pd.NaT
    return out


def ticker_in_universe(
    ticker: str,
    as_of: pd.Timestamp,
    ranges: pd.DataFrame,
) -> bool:
    """True if ticker has an active row covering as_of (inclusive)."""
    tnorm = _tbase(ticker)
    as_of = pd.Timestamp(as_of).normalize()
    tb = ranges["ticker"].map(_tbase)
    sub = ranges[tb == tnorm]
    if sub.empty:
        return False
    for _, row in sub.iterrows():
        start = row["start_date"]
        end = row["end_date"]
        if pd.isna(start):
            continue
        if as_of < start:
            continue
        if pd.isna(end) or as_of <= end:
            return True
    return False


def filter_tickers_by_membership_at_date(
    tickers: list[str],
    as_of: pd.Timestamp,
    ranges: pd.DataFrame,
) -> list[str]:
    return [t for t in tickers if ticker_in_universe(t, as_of, ranges)]


def filter_tickers_full_history(
    tickers: list[str],
    period: str,
    min_bars: int,
    fetch_close,
) -> tuple[list[str], list[str]]:
    """
    Keep tickers whose adjusted close series has at least min_bars rows.

    fetch_close: callable(ticker, period) -> pd.Series | None (e.g. fetch_ohlcv_safe)
    Returns (kept, dropped).
    """
    kept: list[str] = []
    dropped: list[str] = []
    for t in tickers:
        try:
            s = fetch_close(t, period)
        except Exception as e:
            logger.debug("full_history fetch failed %s: %s", t, e)
            dropped.append(t)
            continue
        if s is None or len(s.dropna()) < min_bars:
            dropped.append(t)
            continue
        kept.append(t)
    return kept, dropped


def apply_universe_config(
    config: dict,
    tickers: list[str],
    *,
    backend_root: Path | None = None,
    fetch_close=None,
    as_of: pd.Timestamp | None = None,
) -> tuple[list[str], dict[str, Any]]:
    """
    Apply backtest.universe from config. Returns (filtered_tickers, meta).

    meta includes: mode, dropped, note (for logging / JSON)
    """
    backend_root = backend_root or Path(__file__).resolve().parent.parent
    bt = config.get("backtest") or {}
    u = bt.get("universe") or {}
    mode = str(u.get("mode") or "none").lower().strip()
    meta: dict[str, Any] = {"mode": mode, "dropped": [], "note": ""}

    if mode in ("", "none", "off"):
        meta["note"] = "Universe mode none — all input tickers run (no DIY filter)."
        return list(tickers), meta

    if mode == "full_history":
        min_bars = int(u.get("full_history_min_bars") or 500)
        if fetch_close is None:
            from signals.fetcher import fetch_ohlcv_safe

            fetch_close = fetch_ohlcv_safe
        period = (config.get("data") or {}).get("period") or "10y"
        kept, dropped = filter_tickers_full_history(tickers, period, min_bars, fetch_close)
        meta["dropped"] = dropped
        meta["note"] = (
            f"full_history: min_bars={min_bars}, period={period!r}; "
            f"kept {len(kept)}/{len(tickers)} (excludes short/empty history — not full survivorship control)."
        )
        return kept, meta

    if mode == "membership_csv":
        raw_path = u.get("membership_csv")
        path = _resolve_csv_path(str(raw_path) if raw_path else None, backend_root)
        if not path or not path.is_file():
            meta["note"] = f"membership_csv not found: {raw_path!r} — skipping filter."
            logger.warning("backtest.universe.membership_csv missing: %s", raw_path)
            return list(tickers), meta
        ranges = load_membership_ranges_csv(path)
        ref = as_of or pd.Timestamp.utcnow().normalize()
        # Align with typical backtest window start: "honest" for batch = eligible at ref
        ref_cfg = u.get("as_of_date")
        if ref_cfg:
            ref = pd.to_datetime(ref_cfg, utc=False).normalize()
        kept = filter_tickers_by_membership_at_date(tickers, ref, ranges)
        meta["dropped"] = [t for t in tickers if t not in kept]
        meta["note"] = (
            f"membership_csv {path.name} as_of={ref.date()}; "
            f"kept {len(kept)}/{len(tickers)} (you maintain file — not vendor index data)."
        )
        return kept, meta

    meta["note"] = f"Unknown universe mode {mode!r} — no filter."
    return list(tickers), meta
