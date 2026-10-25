"""Intraday band-entry triggers — "alert me when price enters the band".

The dashboard already shows entry bands vs spot; this is the trigger layer:
every scan, compare the latest intraday quote to each ticker's st_band
(from the most recent EOD snapshot row) and emit a `BAND_ENTRY` event the
first time price crosses into the actionable zone that day.

Semantics (kept deliberately conservative):
- "Entered band" = previous check was above band.high AND now price is
  inside [low, high]. Price already inside at first observation doesn't fire
  (it was already there, not an "entry").
- Only fires for tickers whose entry_mode is starter_only / full_go —
  hard_lock rows have no actionable zone to alert on.
- Dedupe: one event per ticker per calendar day (dedupe_key carries the date).

Quotes come from yfinance fast_info (same fetcher the pipeline uses). The
worker calls `check_band_entries(...)` each scan; state lives in
data/alerts/band_state.json so a restart doesn't re-fire.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from alerts.events import AlertEvent
from signals.time_et import today_est

logger = logging.getLogger("alerts.band_triggers")

_ACTIONABLE_MODES = ("starter_only", "full_go")


def _latest_eod_rows(data_root: Path) -> dict[str, dict]:
    """ticker -> row from the newest EOD snapshot on disk."""
    eod_dir = data_root / "eod"
    if not eod_dir.is_dir():
        return {}
    files = sorted(eod_dir.glob("*.json"))
    if not files:
        return {}
    try:
        snap = json.loads(files[-1].read_text(encoding="utf-8"))
    except Exception:
        return {}
    out: dict[str, dict] = {}
    for row in snap.get("run_results") or snap.get("signals") or []:
        if isinstance(row, dict) and row.get("ticker"):
            out[str(row["ticker"]).upper()] = row
    return out


def _quote(symbol: str) -> float | None:
    try:
        import yfinance as yf

        info = yf.Ticker(symbol).fast_info
        p = getattr(info, "last_price", None) or getattr(info, "lastPrice", None)
        return float(p) if p else None
    except Exception:
        return None


class BandTriggerEngine:
    def __init__(self, data_root: Path):
        self.state_path = data_root / "alerts" / "band_state.json"
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state = self._load()

    def _load(self) -> dict:
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save(self) -> None:
        try:
            self.state_path.write_text(json.dumps(self.state), encoding="utf-8")
        except Exception as e:
            logger.warning("band_state save failed: %s", e)

    def check(self, symbols: list[str]) -> list[AlertEvent]:
        """Return BAND_ENTRY events for tickers whose price just crossed into the band."""
        rows = _latest_eod_rows(self.state_path.parent.parent)
        if not rows:
            return []
        today = today_est()
        fired = self.state.get(today) or set()
        events: list[AlertEvent] = []

        for sym in symbols:
            sym = sym.upper()
            row = rows.get(sym)
            if not row or sym in fired:
                continue
            em = str(row.get("entry_mode") or "").lower()
            if em not in _ACTIONABLE_MODES:
                continue
            band = row.get("st_band") or {}
            lo, hi = band.get("low"), band.get("high")
            try:
                lo, hi = float(lo), float(hi)
            except (TypeError, ValueError):
                continue
            if hi <= lo:
                continue
            price = _quote(sym)
            if price is None:
                continue
            prev = self.state.get(f"prev_{sym}")
            inside_now = lo <= price <= hi
            if inside_now and (prev is None or prev > hi):
                events.append(
                    AlertEvent.create(
                        ticker=sym,
                        alert_type="BAND_ENTRY",
                        severity="HIGH",
                        title=f"{sym} entered entry band",
                        message=(
                            f"Spot ${price:.2f} is inside the short entry band "
                            f"${lo:.2f}–${hi:.2f} (entry_mode={em}) — staged tranche trigger."
                        ),
                        payload={"price": price, "band_low": lo, "band_high": hi, "entry_mode": em},
                        dedupe_key=f"{sym}:BAND_ENTRY:{today}",
                    )
                )
                fired.add(sym)
            self.state[f"prev_{sym}"] = price

        self.state[today] = list(fired)
        self._save()  # persist prev prices (edge detection) + fired set
        return events
