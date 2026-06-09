from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from alerts.tradier_client import TradierClient
from alerts.iv_store import IVHistoryFileStore, IVSnapshot

logger = logging.getLogger("alerts.engine")


@dataclass(frozen=True)
class IVMetrics:
    current_iv: float
    iv_rank: float
    iv_percentile: float
    iv_high: float
    iv_low: float
    is_proxy: bool


def _compute_iv_metrics(series: list[tuple[date, float]]) -> IVMetrics | None:
    if not series:
        return None
    vals = [iv for _, iv in series if iv and iv > 0]
    if not vals:
        return None
    cur = float(vals[-1])
    hi = float(max(vals))
    lo = float(min(vals))
    rng = hi - lo
    iv_rank = ((cur - lo) / rng * 100.0) if rng > 1e-9 else 50.0
    below = sum(1 for v in vals if v < cur)
    iv_pct = (below / len(vals)) * 100.0 if vals else 50.0
    # Proxy until we have enough history (about 60 days feels usable)
    is_proxy = len(vals) < 60
    return IVMetrics(
        current_iv=round(cur, 4),
        iv_rank=round(iv_rank, 1),
        iv_percentile=round(iv_pct, 1),
        iv_high=round(hi, 4),
        iv_low=round(lo, 4),
        is_proxy=is_proxy,
    )


def _extract_atm_iv(options: list[dict], price: float) -> float | None:
    if not options or not price:
        return None
    calls = [o for o in options if (o.get("option_type") or "").lower() == "call"]
    if not calls:
        return None
    # Pick the call closest to spot; use its strike to find matching put
    try:
        atm_call = min(calls, key=lambda o: abs(float(o.get("strike", 0)) - price))
        strike = float(atm_call.get("strike", 0))
    except Exception:
        return None

    def _iv(o: dict) -> float:
        g = o.get("greeks") or {}
        return float(g.get("smv_vol") or o.get("implied_volatility") or 0.0)

    call_iv = _iv(atm_call)
    put = next(
        (o for o in options if (o.get("option_type") or "").lower() == "put" and float(o.get("strike", 0)) == strike),
        None,
    )
    put_iv = _iv(put) if put else call_iv
    iv = (call_iv + put_iv) / 2.0 if (call_iv and put_iv) else (call_iv or put_iv)
    return float(iv) if iv and iv > 0 else None


class OptionsAlertsEngine:
    """
    Core scanning engine.

    Philosophy:
      - Intraday scans should be cheap: quotes + macro + stored IV metrics.
      - Daily refresh job updates IV snapshots (ATM IV) so IV Rank becomes real over time.
    """

    def __init__(self, *, data_root: Path):
        self.client = TradierClient.from_env()
        self.iv_store = IVHistoryFileStore(data_root / "alerts")

    def refresh_daily_iv_snapshots(self, symbols: list[str]) -> dict[str, Any]:
        """
        Daily job: fetch chain once per symbol and append today's ATM IV snapshot.
        """
        out: dict[str, Any] = {"updated": 0, "skipped": 0, "errors": {}}
        today = date.today()
        quotes = self._get_quotes_map(symbols)

        for sym in symbols:
            price = quotes.get(sym)
            if not price:
                out["skipped"] += 1
                continue
            try:
                exp = self._pick_expiration(sym)
                if not exp:
                    out["skipped"] += 1
                    continue
                chain = self.client.options_chain(sym, exp, greeks=True)
                options = chain.get("options", {}).get("option", []) or []
                iv = _extract_atm_iv(options, float(price))
                if iv is None:
                    out["skipped"] += 1
                    continue
                self.iv_store.append(IVSnapshot(symbol=sym, as_of=today, atm_iv=float(iv)))
                out["updated"] += 1
            except Exception as e:
                out["errors"][sym] = str(e)
        return out

    def scan_watchlist(self, symbols: list[str]) -> dict[str, Any]:
        """
        Intraday scan: uses stored IV metrics + current quotes. Avoids per-symbol chain calls.
        """
        quotes = self._get_quotes_map(symbols)
        now = __import__("signals.time_et", fromlist=["now_iso_et"]).now_iso_et()
        signals: list[dict[str, Any]] = []

        for sym in symbols:
            price = quotes.get(sym)
            series = self.iv_store.load_series(sym)
            ivm = _compute_iv_metrics(series)
            if price is None:
                continue

            signals.append(
                {
                    "ticker": sym,
                    "price": round(float(price), 2),
                    "iv_rank": ivm.iv_rank if ivm else None,
                    "iv_percentile": ivm.iv_percentile if ivm else None,
                    "current_iv": ivm.current_iv if ivm else None,
                    "iv_proxy": bool(ivm.is_proxy) if ivm else True,
                    "as_of": now,
                }
            )

        return {"as_of": now, "signals": signals}

    def _get_quotes_map(self, symbols: list[str]) -> dict[str, float]:
        try:
            resp = self.client.quotes(symbols)
            q = resp.get("quotes", {}).get("quote")
            out: dict[str, float] = {}
            if isinstance(q, list):
                for row in q:
                    sym = (row.get("symbol") or "").upper()
                    last = row.get("last") or row.get("bid") or row.get("ask")
                    if sym and last is not None:
                        out[sym] = float(last)
            elif isinstance(q, dict):
                sym = (q.get("symbol") or "").upper()
                last = q.get("last") or q.get("bid") or q.get("ask")
                if sym and last is not None:
                    out[sym] = float(last)
            return out
        except Exception as e:
            logger.warning("quotes failed: %s", e)
            return {}

    def _pick_expiration(self, symbol: str) -> str | None:
        try:
            resp = self.client.options_expirations(symbol)
            dates = resp.get("expirations", {}).get("date", []) or []
            if not dates:
                return None
            return str(dates[0])
        except Exception:
            return None

