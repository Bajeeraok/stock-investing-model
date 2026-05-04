"""
Paper Trade Logger
------------------
Lightweight "start today" logging of model signals and outcomes.

Design goal: integrate with existing EOD snapshot infrastructure so we can backfill
outcomes without additional API calls (aligns with forward_tracking).

Storage: paper_trades.csv and MTM files live under data_root (get_data_root()).
Set env DATA_ROOT to a persistent path (e.g. mounted volume) so paper trades and
EOD files survive backend restarts and redeploys. EOD is also read from Redis when
available, so mark-to-market and outcomes can work when Redis has snapshots even if
the local data/eod directory is ephemeral.

Key methods:
  - log_signal(...)              : append (idempotent per date+ticker+signal)
  - fill_outcomes(...)           : backfill outcome at first EOD on/after signal_date + N business days
  - get_performance_summary(...) : win-rate once enough completed trades exist

Entry price (log_signals_from_results):
  - Prefer ``paper_entry_price`` when the dashboard sets it from FMP batch or Yahoo last (aligned with marks).
  - Else ``close`` / ``price`` from run_signals = last bar of the OHLCV series used for indicators.
"""

from __future__ import annotations

import csv
import json
import logging
import hashlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from pandas.tseries.offsets import BDay

logger = logging.getLogger(__name__)


def _default_data_root() -> Path:
    # backend/signals/ -> backend/
    return Path(__file__).resolve().parent.parent / "data"


def _paper_file(data_root: Path | None = None) -> Path:
    root = data_root or _default_data_root()
    root.mkdir(parents=True, exist_ok=True)
    return root / "paper_trades.csv"


def _eod_dir(data_root: Path | None = None) -> Path:
    root = data_root or _default_data_root()
    d = root / "eod"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _mtm_history_file(data_root: Path | None = None) -> Path:
    root = data_root or _default_data_root()
    root.mkdir(parents=True, exist_ok=True)
    return root / "paper_trades_mtm.jsonl"


def _mtm_index_file(data_root: Path | None = None) -> Path:
    root = data_root or _default_data_root()
    root.mkdir(parents=True, exist_ok=True)
    return root / "paper_trades_mtm_index.json"


_FIELDS = [
    "trade_id",
    "date",
    "ticker",
    "signal",
    "ml_confidence",
    "regime",
    "entry_price",
    "entry_price_source",
    "effective_entry_date",
    "effective_entry_price",
    "effective_entry_source",
    "execution_mode",
    "entry_cost_pct",
    "exit_cost_pct",
    "target_1",
    "hard_stop",
    "atr_14",
    "model_score",
    "kelly_pct",
    # Outcome (filled later)
    "horizon_trading_days",
    "next_date",
    "actual_price",
    "actual_price_net",
    "return_pct",
    "hit_target",
    "hit_stop",
    "outcome",
    # Mark-to-market (filled daily from latest EOD snapshot)
    "mtm_date",
    "mtm_price",
    "mtm_price_net",
    "mtm_return_pct",
    # Rolling daily reference (compare signal-date entry vs latest close)
    "rolling_entry_price",
    "rolling_pnl",
    "rolling_return_pct",
]


def _safe_float(x: Any) -> float | None:
    try:
        if x is None:
            return None
        return float(x)
    except Exception:
        return None


def _run_results_by_ticker_upper(run_results: list) -> dict[str, Any]:
    """Index EOD run_results by uppercase ticker so lookups match paper_trades rows."""
    out: dict[str, Any] = {}
    for r in run_results or []:
        if not isinstance(r, dict):
            continue
        sym = r.get("ticker")
        if not sym:
            continue
        out[str(sym).upper()] = r
    return out


def _today_str() -> str:
    """US market session date — matches EOD snapshot filenames (run_daily uses America/New_York)."""
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")
    except Exception:
        return datetime.now().strftime("%Y-%m-%d")


def _trade_id(date: str, ticker: str, signal: str) -> str:
    raw = f"{date}|{ticker}|{signal}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:12]


def _first_eod_on_or_after(dates: list[str], target: str) -> str | None:
    """First snapshot date string >= target (YYYY-MM-DD)."""
    try:
        ts = pd.Timestamp(target).normalize()
    except Exception:
        return None
    for d in dates:
        try:
            if pd.Timestamp(d).normalize() >= ts:
                return d
        except Exception:
            continue
    return None


def _is_buy_side_signal(sig: str) -> bool:
    """STRONG BUY / BUY / HOLD/ADD — for actionable performance slice (excludes TRIM/REDUCE/WATCH/HOLD)."""
    s = (sig or "").upper()
    if any(x in s for x in ("TRIM", "SELL", "REDUCE", "AVOID")):
        return False
    if s.strip() in ("HOLD", "WATCH"):
        return False
    return "STRONG BUY" in s or s.strip() == "BUY" or "HOLD/ADD" in s


@dataclass
class PaperTradeRecord:
    date: str
    ticker: str
    signal: str
    ml_confidence: float | None
    regime: str | None
    entry_price: float | None
    entry_price_source: str | None
    target_1: float | None
    hard_stop: float | None
    atr_14: float | None
    model_score: float | None
    kelly_pct: float | None
    horizon_trading_days: int = 20  # ~30 calendar days

    def to_row(self) -> dict[str, Any]:
        tid = _trade_id(self.date, self.ticker, self.signal)
        return {
            "trade_id": tid,
            "date": self.date,
            "ticker": self.ticker,
            "signal": self.signal,
            "ml_confidence": self.ml_confidence,
            "regime": self.regime,
            "entry_price": self.entry_price,
            "entry_price_source": self.entry_price_source,
            "target_1": self.target_1,
            "hard_stop": self.hard_stop,
            "atr_14": self.atr_14,
            "model_score": self.model_score,
            "kelly_pct": self.kelly_pct,
            "horizon_trading_days": self.horizon_trading_days,
            "next_date": None,
            "actual_price": None,
            "return_pct": None,
            "hit_target": None,
            "outcome": None,
            "mtm_date": None,
            "mtm_price": None,
            "mtm_return_pct": None,
            "rolling_entry_price": None,
            "rolling_pnl": None,
            "rolling_return_pct": None,
        }


class PaperTradeLogger:
    def __init__(self, data_root: Path | None = None, execution_cfg: dict[str, Any] | None = None):
        self.data_root = data_root or _default_data_root()
        self.path = _paper_file(self.data_root)
        self.execution_cfg = execution_cfg or {}
        mode = str(self.execution_cfg.get("mode", "close_to_close")).strip().lower()
        if mode not in ("close_to_close", "next_session"):
            mode = "close_to_close"
        self.execution_mode = mode
        # Per-side cost is applied on entry and exit independently.
        # Supports either explicit per-side config or round-trip shorthand.
        rt = _safe_float(self.execution_cfg.get("round_trip_cost_pct"))
        per_side = _safe_float(self.execution_cfg.get("per_side_cost_pct"))
        if per_side is None and rt is not None and rt >= 0:
            per_side = rt / 2.0
        self.cost_per_side_pct = max(0.0, float(per_side or 0.0))
        self.use_intraday_touch = bool(self.execution_cfg.get("use_intraday_touch", True))
        self._init_file()

    def _init_file(self) -> None:
        if self.path.exists():
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=_FIELDS)
            w.writeheader()

    def _read_all(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            self._init_file()
            return []
        try:
            with open(self.path, "r", newline="", encoding="utf-8") as f:
                r = csv.DictReader(f)
                return [dict(row) for row in r]
        except Exception as e:
            logger.debug("paper_trades read failed: %s", e)
            return []

    def _write_all(self, rows: list[dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        for row in rows:
            self._ensure_trade_id(row)
        with open(self.path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=_FIELDS)
            w.writeheader()
            for row in rows:
                # Ensure all fields exist (CSV stability)
                out = {k: row.get(k) for k in _FIELDS}
                w.writerow(out)

    @staticmethod
    def _dedupe_key(row: dict[str, Any]) -> tuple[str, str, str]:
        return (str(row.get("date") or ""), str(row.get("ticker") or ""), str(row.get("signal") or ""))

    @staticmethod
    def _ensure_trade_id(row: dict[str, Any]) -> str:
        tid = str(row.get("trade_id") or "").strip()
        if tid:
            return tid
        d = str(row.get("date") or "")
        t = str(row.get("ticker") or "")
        s = str(row.get("signal") or "")
        tid = _trade_id(d, t, s)
        row["trade_id"] = tid
        return tid

    def log_signal(self, rec: PaperTradeRecord) -> bool:
        """
        Append a signal row.
        Idempotent per (date, ticker, signal) to avoid duplicates on dashboard refresh.
        Returns True if appended, False if skipped.
        """
        rows = self._read_all()
        key = (rec.date, rec.ticker, rec.signal)
        existing = {self._dedupe_key(r) for r in rows}
        if key in existing:
            return False
        rows.append(rec.to_row())
        self._write_all(rows)
        return True

    def log_signals_from_results(
        self,
        results: list[dict[str, Any]],
        date_str: str | None = None,
        horizon_trading_days: int = 20,
        only_actionable: bool = False,
    ) -> dict[str, Any]:
        """
        Convenience: log signals from dashboard run_signals() output.
        """
        date_str = date_str or _today_str()
        n_appended = 0
        n_seen = 0
        for r in results or []:
            try:
                t = (r.get("ticker") or "").upper().strip()
                if not t or r.get("error"):
                    continue
                sig = r.get("signal") or r.get("short_suggestion") or "HOLD"
                if only_actionable and str(sig).upper() not in ("BUY", "STRONG BUY", "HOLD/ADD"):
                    continue
                n_seen += 1
                st = r.get("st_band") if isinstance(r.get("st_band"), dict) else None
                target_1 = _safe_float(st.get("high")) if st else None
                hard_stop = _safe_float(st.get("low")) if st else None
                ml = r.get("ml_short_prob")
                ml_conf = round(float(ml) * 100, 1) if _safe_float(ml) is not None else None
                # Prefer global market regime if present (Tier1 regime scale)
                reg = r.get("_global_market_regime") or r.get("regime")
                # Entry: dashboard may set paper_entry_price from batch/Yahoo last — else OHLCV last bar (close)
                entry = _safe_float(
                    r.get("paper_entry_price") or r.get("close") or r.get("price")
                )
                entry_src = None
                if _safe_float(r.get("paper_entry_price")) is not None:
                    entry_src = str(r.get("paper_entry_source") or "live_quote")
                elif entry is not None:
                    entry_src = "ohlcv_last_bar"
                atr_14 = _safe_float(r.get("atr_14"))
                score = _safe_float(r.get("composite_buy"))
                # kelly_pct is optional; if Tier1 sizing is available elsewhere we can backfill later
                rec = PaperTradeRecord(
                    date=date_str,
                    ticker=t,
                    signal=str(sig),
                    ml_confidence=ml_conf,
                    regime=str(reg) if reg is not None else None,
                    entry_price=round(entry, 2) if entry is not None else None,
                    entry_price_source=entry_src,
                    target_1=round(target_1, 2) if target_1 is not None else None,
                    hard_stop=round(hard_stop, 2) if hard_stop is not None else None,
                    atr_14=round(atr_14, 2) if atr_14 is not None else None,
                    model_score=round(score, 1) if score is not None else None,
                    kelly_pct=None,
                    horizon_trading_days=horizon_trading_days,
                )
                if self.log_signal(rec):
                    n_appended += 1
            except Exception:
                continue
        return {"date": date_str, "seen": n_seen, "appended": n_appended}

    def _row_mode(self, row: dict[str, Any]) -> str:
        m = str(row.get("execution_mode") or self.execution_mode or "close_to_close").strip().lower()
        return m if m in ("close_to_close", "next_session") else "close_to_close"

    def _row_cost_pct(self, row: dict[str, Any], key: str) -> float:
        # Stored as percent in CSV for readability; convert to fraction.
        v = _safe_float(row.get(key))
        if v is None:
            return self.cost_per_side_pct
        return max(0.0, float(v) / 100.0)

    def _ensure_effective_entry(self, row: dict[str, Any], dates: list[str]) -> tuple[float | None, str | None]:
        """
        Ensure row has an effective entry (fill model + entry cost).
        Returns (effective_entry_price, effective_entry_date).
        """
        eff = _safe_float(row.get("effective_entry_price"))
        eff_date = str(row.get("effective_entry_date") or "").strip() or None
        if eff is not None and eff > 0 and eff_date:
            return eff, eff_date

        mode = self._row_mode(row)
        signal_date = str(row.get("date") or "")
        entry_cost = self._row_cost_pct(row, "entry_cost_pct")
        next_session_date: str | None = None

        base_px = None
        base_date = None
        base_src = None

        if mode == "next_session":
            try:
                target_ts = pd.Timestamp(signal_date).normalize() + BDay(1)
                next_session_date = target_ts.strftime("%Y-%m-%d")
            except Exception:
                target_ts = None
            if target_ts is not None:
                for d in dates:
                    try:
                        if pd.Timestamp(d).normalize() >= target_ts:
                            px = self._ticker_close_on_snapshot(d, str(row.get("ticker") or ""))
                            if px is not None and px > 0:
                                base_px = float(px)
                                base_date = d
                                base_src = "next_session_close"
                                break
                    except Exception:
                        continue

        if base_px is None:
            base_px = _safe_float(row.get("entry_price"))
            if base_px is not None and base_px > 0:
                if mode == "next_session" and next_session_date:
                    # Next-session mode with no next snapshot yet:
                    # keep planned effective date so MTM doesn't start too early.
                    base_date = next_session_date
                else:
                    base_date = _first_eod_on_or_after(dates, signal_date) or signal_date
                base_src = str(row.get("entry_price_source") or "signal_entry")

        if base_px is None or base_px <= 0 or not base_date:
            return None, None

        eff_px = round(float(base_px) * (1.0 + entry_cost), 4)
        row["entry_price"] = round(float(base_px), 2)
        row["effective_entry_price"] = eff_px
        row["effective_entry_date"] = base_date
        row["effective_entry_source"] = base_src
        row["execution_mode"] = mode
        row["entry_cost_pct"] = round(entry_cost * 100, 4)
        row["exit_cost_pct"] = round(self._row_cost_pct(row, "exit_cost_pct") * 100, 4)
        return eff_px, base_date

    def sync_targets_stops_from_results(self, results: list[dict[str, Any]] | None = None, max_rows: int = 500) -> dict[str, Any]:
        """
        Update target_1 and hard_stop for open trades from the latest model output.
        Entry price is left unchanged (cost basis = price at signal date).

        If results is provided (e.g. from run_signals), use that; else use latest EOD snapshot run_results.
        """
        rows = self._read_all()
        if not rows:
            return {"updated": 0, "message": "No paper trades logged yet."}

        run_by_ticker: dict[str, dict] = {}
        if results is not None:
            for r in (results or []):
                if isinstance(r, dict) and r.get("ticker"):
                    run_by_ticker[(r.get("ticker") or "").upper()] = r
        else:
            dates = self._list_eod_dates()
            if not dates:
                return {"updated": 0, "message": "No EOD snapshots; pass results or run EOD first."}
            snap = self._load_snapshot(dates[-1])
            if snap:
                for r in (snap.get("run_results") or []):
                    if isinstance(r, dict) and r.get("ticker"):
                        run_by_ticker[(r.get("ticker") or "").upper()] = r

        if not run_by_ticker:
            return {"updated": 0, "message": "No run results to sync from."}

        updated = 0
        for row in rows[:max_rows]:
            try:
                if row.get("outcome"):
                    continue
                t = (row.get("ticker") or "").upper()
                run = run_by_ticker.get(t)
                if not run:
                    continue
                st = run.get("st_band") if isinstance(run.get("st_band"), dict) else None
                if not st:
                    continue
                target_1 = _safe_float(st.get("high"))
                hard_stop = _safe_float(st.get("low"))
                changed = False
                if target_1 is not None:
                    row["target_1"] = round(target_1, 2)
                    changed = True
                if hard_stop is not None:
                    row["hard_stop"] = round(hard_stop, 2)
                    changed = True
                if changed:
                    updated += 1
            except Exception:
                continue

        if updated:
            self._write_all(rows)
        return {"updated": updated, "message": None}

    # ----- Outcomes (backfill) -----
    # EOD dates/snapshots: use Redis first (persists across deploys), then files under DATA_ROOT.
    # So paper PnL works when EOD is in Redis even if backend/data/eod is ephemeral.

    def _list_eod_dates(self) -> list[str]:
        seen: set[str] = set()
        dates: list[str] = []
        try:
            from signals.cache import list_eod_dates_redis
            for d in list_eod_dates_redis():
                if d not in seen and len(d) == 10 and d[4] == "-" and d[7] == "-":
                    seen.add(d)
                    dates.append(d)
        except Exception:
            pass
        d = _eod_dir(self.data_root)
        if d.exists():
            for p in d.glob("*.json"):
                try:
                    stem = p.stem
                    if stem not in seen and len(stem) == 10 and stem[4] == "-" and stem[7] == "-":
                        seen.add(stem)
                        dates.append(stem)
                except Exception:
                    pass
        return sorted(set(dates))

    def _load_snapshot(self, date_str: str) -> dict | None:
        try:
            from signals.cache import get_eod_snapshot_redis
            data = get_eod_snapshot_redis(date_str)
            if data and isinstance(data, dict) and data.get("run_results") is not None:
                return data
        except Exception:
            pass
        p = _eod_dir(self.data_root) / f"{date_str}.json"
        if not p.exists():
            return None
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def _ticker_close_on_snapshot(self, date_str: str, ticker: str) -> float | None:
        snap = self._load_snapshot(date_str)
        if not snap:
            return None
        want = ticker.upper()
        for r in snap.get("run_results") or []:
            if not isinstance(r, dict):
                continue
            if str(r.get("ticker") or "").upper() == want:
                return _safe_float(r.get("close"))
        return None

    def _benchmark_return_pct_between(
        self,
        signal_date: str,
        end_date: str,
        benchmark: str = "SPY",
    ) -> float | None:
        """Return % of benchmark from first EOD on/after signal_date to close on end_date snapshot."""
        dates = self._list_eod_dates()
        if len(dates) < 2:
            return None
        start_d = _first_eod_on_or_after(dates, signal_date)
        if not start_d:
            return None
        try:
            if pd.Timestamp(end_date).normalize() < pd.Timestamp(start_d).normalize():
                end_date = dates[-1]
        except Exception:
            pass
        p0 = self._ticker_close_on_snapshot(start_d, benchmark)
        p1 = self._ticker_close_on_snapshot(end_date, benchmark)
        if p0 is None or p1 is None or p0 <= 0:
            return None
        return round(100.0 * (p1 - p0) / p0, 2)

    def enrich_trades_with_benchmark(self, rows: list[dict[str, Any]], benchmark: str = "SPY") -> list[dict[str, Any]]:
        """
        Add benchmark_return_pct (same window as trade MTM or completed outcome) and excess_return_pct.
        Modifies rows in place.
        """
        dates = self._list_eod_dates()
        bench = benchmark.upper()
        for r in rows:
            r["benchmark_ticker"] = bench
            if len(dates) < 2:
                r["benchmark_return_pct"] = None
                r["excess_return_pct"] = None
                continue
            start_ref = str(r.get("effective_entry_date") or r.get("date") or "")
            start_d = _first_eod_on_or_after(dates, start_ref)
            if not start_d:
                r["benchmark_return_pct"] = None
                r["excess_return_pct"] = None
                continue
            if str(r.get("outcome") or "") in ("HIT", "MISS", "STOP_HIT") and r.get("next_date"):
                end_d = str(r.get("next_date"))
            else:
                end_d = str(r.get("mtm_date") or dates[-1])
            try:
                if pd.Timestamp(end_d).normalize() < pd.Timestamp(start_d).normalize():
                    end_d = dates[-1]
            except Exception:
                pass
            br = self._benchmark_return_pct_between(start_ref, end_d, bench)
            r["benchmark_return_pct"] = br
            tr = None
            if str(r.get("outcome") or "") in ("HIT", "MISS", "STOP_HIT") and _safe_float(r.get("return_pct")) is not None:
                tr = float(r["return_pct"])
            elif _safe_float(r.get("mtm_return_pct")) is not None:
                tr = float(r["mtm_return_pct"])
            r["excess_return_pct"] = round(tr - br, 2) if (tr is not None and br is not None) else None
        return rows

    def fill_outcomes(self, max_rows: int = 500) -> dict[str, Any]:
        """
        Backfill outcomes using EOD snapshots (no extra API calls).
        Uses horizon_trading_days to find the next snapshot date.
        """
        rows = self._read_all()
        if not rows:
            return {"updated": 0, "message": "No paper trades logged yet."}

        dates = self._list_eod_dates()
        if len(dates) < 2:
            return {"updated": 0, "message": "Need at least 2 EOD snapshots (Redis or data/eod) to fill outcomes."}

        updated = 0
        for row in rows[:max_rows]:
            try:
                if row.get("outcome"):
                    continue
                as_of = row.get("date")
                if not as_of:
                    continue
                eff_entry, eff_entry_date = self._ensure_effective_entry(row, dates)
                if eff_entry is None or not eff_entry_date:
                    continue
                horizon = int(float(row.get("horizon_trading_days") or 20))
                # First EOD snapshot on or after (as_of + N business days) — not "N rows" in the list
                # (avoids mis-counting when some calendar days lack a snapshot).
                try:
                    target_ts = pd.Timestamp(eff_entry_date).normalize() + BDay(horizon)
                except Exception:
                    continue
                next_date = None
                for d in dates:
                    if pd.Timestamp(d).normalize() >= target_ts:
                        next_date = d
                        break
                if not next_date:
                    continue

                snap = self._load_snapshot(next_date)
                if not snap:
                    continue
                run_by_ticker = _run_results_by_ticker_upper(snap.get("run_results") or [])
                t = (row.get("ticker") or "").upper()
                r_next = run_by_ticker.get(t)
                actual = _safe_float((r_next or {}).get("close"))
                if actual is None or eff_entry <= 0:
                    continue

                exit_cost = self._row_cost_pct(row, "exit_cost_pct")
                actual_net = round(float(actual) * (1.0 - exit_cost), 4)
                ret_pct = round(100 * (actual_net - eff_entry) / eff_entry, 2)
                tgt = _safe_float(row.get("target_1"))
                stop = _safe_float(row.get("hard_stop"))
                hi = _safe_float((r_next or {}).get("high"))
                lo = _safe_float((r_next or {}).get("low"))
                hit_target = None
                hit_stop = None
                if tgt is not None:
                    if self.use_intraday_touch and hi is not None:
                        hit_target = 1 if hi >= tgt else 0
                    else:
                        hit_target = 1 if actual >= tgt else 0
                if stop is not None:
                    if self.use_intraday_touch and lo is not None:
                        hit_stop = 1 if lo <= stop else 0
                    else:
                        hit_stop = 1 if actual <= stop else 0

                if hit_stop == 1:
                    outcome = "STOP_HIT"
                elif hit_target is not None:
                    outcome = "HIT" if hit_target == 1 else "MISS"
                else:
                    # No target band recorded — close based on net return direction at horizon
                    outcome = "HIT" if ret_pct >= 0 else "MISS"

                row["next_date"] = next_date
                row["actual_price"] = round(actual, 2)
                row["actual_price_net"] = round(actual_net, 2)
                row["return_pct"] = ret_pct
                row["hit_target"] = hit_target
                row["hit_stop"] = hit_stop
                row["outcome"] = outcome
                updated += 1
            except Exception:
                continue

        if updated:
            self._write_all(rows)
        return {"updated": updated, "message": None}

    def mark_to_market(self, max_rows: int = 500) -> dict[str, Any]:
        """
        Update open trades daily using the latest available EOD snapshot.
        This gives you a running return% even before the 20-trading-day horizon is reached.
        Does not set HIT/MISS; that remains the job of fill_outcomes().
        """
        rows = self._read_all()
        if not rows:
            return {"updated": 0, "message": "No paper trades logged yet."}

        dates = self._list_eod_dates()
        if not dates:
            return {"updated": 0, "message": "No EOD snapshots in Redis or data/eod. Run EOD or upload snapshots."}

        latest = dates[-1]
        snap = self._load_snapshot(latest)
        if not snap:
            return {"updated": 0, "message": f"Latest EOD snapshot unreadable: {latest}"}

        run_by_ticker = _run_results_by_ticker_upper(snap.get("run_results") or [])
        updated = 0

        for row in rows[:max_rows]:
            try:
                if row.get("outcome"):
                    continue
                self._ensure_trade_id(row)
                eff_entry, _eff_date = self._ensure_effective_entry(row, dates)
                if eff_entry is None or eff_entry <= 0:
                    continue
                # Do not MTM a trade before its effective entry date.
                try:
                    if _eff_date and pd.Timestamp(latest).normalize() < pd.Timestamp(_eff_date).normalize():
                        continue
                except Exception:
                    pass
                t = (row.get("ticker") or "").upper()
                r_now = run_by_ticker.get(t)
                px = _safe_float((r_now or {}).get("close"))
                if px is None:
                    continue
                exit_cost = self._row_cost_pct(row, "exit_cost_pct")
                px_net = round(float(px) * (1.0 - exit_cost), 4)
                mtm_ret = round(100 * (px_net - eff_entry) / eff_entry, 2)
                # Rolling columns: only after we have a prior mark — daily $/% vs last snapshot; first MTM has no prior day.
                prev_mark = _safe_float(row.get("rolling_entry_price"))
                if prev_mark is not None and prev_mark > 0:
                    rolling_ret = round(100 * (px_net - prev_mark) / prev_mark, 2)
                    rolling_pnl = round(px_net - prev_mark, 2)
                else:
                    rolling_ret = None
                    rolling_pnl = None
                # Only write if new snapshot date (reduces file churn on repeated dashboard refresh)
                if str(row.get("mtm_date") or "") == latest:
                    continue
                row["mtm_date"] = latest
                row["mtm_price"] = round(px, 2)
                row["mtm_price_net"] = round(px_net, 2)
                row["mtm_return_pct"] = mtm_ret
                row["rolling_entry_price"] = round(px_net, 2)
                row["rolling_pnl"] = rolling_pnl
                row["rolling_return_pct"] = rolling_ret
                updated += 1
            except Exception:
                continue

        if updated:
            self._write_all(rows)
        return {"updated": updated, "message": None, "as_of": latest}

    def append_mtm_history(self, max_rows: int = 500) -> dict[str, Any]:
        """
        Append one MTM datapoint per open trade per EOD date (idempotent per day).
        Data lives in paper_trades_mtm.jsonl for day-by-day P&L history.
        """
        rows = self._read_all()
        if not rows:
            return {"appended": 0, "message": "No paper trades logged yet."}

        dates = self._list_eod_dates()
        if not dates:
            return {"appended": 0, "message": "No EOD snapshots in Redis or data/eod."}
        latest = dates[-1]

        # Load index so repeated dashboard refreshes don't append duplicates for the same latest date
        idx_path = _mtm_index_file(self.data_root)
        idx = {"as_of": None, "keys": []}
        try:
            if idx_path.exists():
                with open(idx_path, "r", encoding="utf-8") as f:
                    idx = json.load(f) or idx
        except Exception:
            idx = {"as_of": None, "keys": []}
        if idx.get("as_of") != latest:
            idx = {"as_of": latest, "keys": []}
        seen_keys = set(str(k) for k in (idx.get("keys") or []))

        out_path = _mtm_history_file(self.data_root)
        appended = 0
        with open(out_path, "a", encoding="utf-8") as f:
            for row in rows[:max_rows]:
                try:
                    if row.get("outcome"):
                        continue
                    tid = self._ensure_trade_id(row)
                    mtm_date = str(row.get("mtm_date") or "")
                    if mtm_date != latest:
                        continue
                    key = f"{tid}:{latest}"
                    if key in seen_keys:
                        continue
                    payload = {
                        "trade_id": tid,
                        "trade_date": row.get("date"),
                        "ticker": (row.get("ticker") or "").upper(),
                        "signal": row.get("signal"),
                        "mtm_date": latest,
                        "mtm_price": _safe_float(row.get("mtm_price")),
                        "mtm_return_pct": _safe_float(row.get("mtm_return_pct")),
                    }
                    f.write(json.dumps(payload) + "\n")
                    appended += 1
                    seen_keys.add(key)
                except Exception:
                    continue

        # Persist index (bounded size)
        try:
            idx["as_of"] = latest
            idx["keys"] = sorted(list(seen_keys))[:5000]
            with open(idx_path, "w", encoding="utf-8") as f:
                json.dump(idx, f)
        except Exception:
            pass
        return {"appended": appended, "message": None, "as_of": latest}

    def get_mtm_history_map(self, recent_rows: list[dict[str, Any]], limit_per_trade: int = 12) -> dict[str, list[dict[str, Any]]]:
        """
        Returns {trade_id: [{mtm_date, mtm_return_pct, mtm_price}...]} capped per trade.
        """
        want: set[str] = set()
        for r in recent_rows or []:
            try:
                tid = str(r.get("trade_id") or "").strip()
                if not tid:
                    tid = _trade_id(str(r.get("date") or ""), str(r.get("ticker") or ""), str(r.get("signal") or ""))
                    r["trade_id"] = tid
                want.add(tid)
            except Exception:
                continue
        if not want:
            return {}

        p = _mtm_history_file(self.data_root)
        if not p.exists():
            return {}

        out: dict[str, list[dict[str, Any]]] = {tid: [] for tid in want}
        try:
            with open(p, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        obj = json.loads(line)
                        tid = str(obj.get("trade_id") or "")
                        if tid not in want:
                            continue
                        out[tid].append(
                            {
                                "mtm_date": obj.get("mtm_date"),
                                "mtm_return_pct": _safe_float(obj.get("mtm_return_pct")),
                                "mtm_price": _safe_float(obj.get("mtm_price")),
                            }
                        )
                    except Exception:
                        continue
            for tid in list(out.keys()):
                out[tid] = out[tid][-limit_per_trade:]
            return out
        except Exception:
            return {}

    def _stats_for_completed(self, completed: list[dict[str, Any]], benchmark: str = "SPY") -> dict[str, Any]:
        returns = [float(r["return_pct"]) for r in completed if _safe_float(r.get("return_pct")) is not None]
        hits: list[int] = []
        for r in completed:
            ht = str(r.get("hit_target") or "").strip()
            if ht != "":
                try:
                    hits.append(int(float(ht)))
                    continue
                except Exception:
                    pass
            oc = str(r.get("outcome") or "").upper()
            if oc == "HIT":
                hits.append(1)
            elif oc in ("MISS", "STOP_HIT"):
                hits.append(0)
        win_rate = round(100 * (sum(hits) / len(hits)), 1) if hits else None
        avg_return = round(sum(returns) / len(returns), 2) if returns else None
        wins = [float(r["return_pct"]) for r in completed if str(r.get("hit_target")) == "1" and _safe_float(r.get("return_pct")) is not None]
        losses = [float(r["return_pct"]) for r in completed if str(r.get("hit_target")) == "0" and _safe_float(r.get("return_pct")) is not None]
        avg_win = round(sum(wins) / len(wins), 2) if wins else None
        avg_loss = round(sum(losses) / len(losses), 2) if losses else None
        excesses: list[float] = []
        for r in completed:
            br = self._benchmark_return_pct_between(
                str(r.get("date") or ""),
                str(r.get("next_date") or ""),
                benchmark,
            )
            tr = _safe_float(r.get("return_pct"))
            if br is not None and tr is not None:
                excesses.append(tr - br)
        avg_excess = round(sum(excesses) / len(excesses), 2) if excesses else None
        return {
            "completed_n": len(completed),
            "win_rate_pct": win_rate,
            "avg_return_pct": avg_return,
            "avg_win_pct": avg_win,
            "avg_loss_pct": avg_loss,
            "avg_excess_vs_spy_pct": avg_excess,
            "n_with_benchmark": len(excesses),
        }

    def get_performance_summary(
        self,
        min_completed: int = 60,
        min_actionable: int = 8,
        benchmark: str = "SPY",
    ) -> dict[str, Any]:
        """
        Aggregate stats on completed (HIT/MISS) trades. Requires min_completed for full ``ok`` status;
        shows preview when 5+ completed but below min. Adds buy-side-only slice (STRONG BUY / BUY / HOLD/ADD).
        """
        rows = self._read_all()
        completed = [r for r in rows if r.get("outcome") in ("HIT", "MISS", "STOP_HIT") and _safe_float(r.get("return_pct")) is not None]

        horizon_note = (
            "Completed trades: exit = first EOD on or after signal date + N business days "
            "(per-row horizon_trading_days, default 20). Compare to SPY over the same dates."
        )

        out: dict[str, Any] = {
            "horizon_note": horizon_note,
            "benchmark_ticker": benchmark.upper(),
            "min_required": min_completed,
            "completed": len(completed),
        }

        # Need enough rows for basic stats; cap at 5 for default (60) runs, allow 3 when caller passes min_completed=3 (e.g. paper vs forward drift).
        stats_floor = max(3, min(5, int(min_completed)))
        if len(completed) < stats_floor:
            out["status"] = f"Need more data: {len(completed)}/{min_completed} completed trades"
            out["message"] = None
            return out

        stats = self._stats_for_completed(completed, benchmark)
        buy_only = [r for r in completed if _is_buy_side_signal(str(r.get("signal") or ""))]
        buy_stats = None
        if len(buy_only) >= min_actionable:
            buy_stats = self._stats_for_completed(buy_only, benchmark)
            buy_stats["label"] = "STRONG BUY / BUY / HOLD/ADD only"

        preview = len(completed) < min_completed
        out["status"] = "preview" if preview else "ok"
        if preview:
            out["message"] = f"Preview ({len(completed)}/{min_completed} completed — need more for full read)"
        else:
            out["message"] = None

        out["win_rate_pct"] = stats["win_rate_pct"]
        out["avg_return_pct"] = stats["avg_return_pct"]
        out["avg_win_pct"] = stats["avg_win_pct"]
        out["avg_loss_pct"] = stats["avg_loss_pct"]
        out["avg_excess_vs_spy_pct"] = stats["avg_excess_vs_spy_pct"]
        out["n_benchmarked"] = stats["n_with_benchmark"]

        if buy_stats:
            out["buy_signals_summary"] = {
                "completed_n": buy_stats["completed_n"],
                "win_rate_pct": buy_stats["win_rate_pct"],
                "avg_return_pct": buy_stats["avg_return_pct"],
                "avg_excess_vs_spy_pct": buy_stats["avg_excess_vs_spy_pct"],
                "label": buy_stats["label"],
            }

        return out

    def get_recent(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = self._read_all()
        for row in rows:
            self._ensure_trade_id(row)
        # newest last in file; return newest first
        out = list(reversed(rows))[:limit]
        return out

