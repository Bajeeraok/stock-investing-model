"""
Paper Trade Logger
------------------
Lightweight "start today" logging of model signals and outcomes.

Design goal: integrate with existing EOD snapshot infrastructure so we can backfill
outcomes without additional API calls (aligns with forward_tracking).

Key methods:
  - log_signal(...)              : append (idempotent per date+ticker+signal)
  - fill_outcomes(...)           : backfill ~30d outcome (default 20 trading days via EOD snapshots)
  - get_performance_summary(...) : win-rate once enough completed trades exist
"""

from __future__ import annotations

import csv
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

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


_FIELDS = [
    "date",
    "ticker",
    "signal",
    "ml_confidence",
    "regime",
    "entry_price",
    "target_1",
    "hard_stop",
    "atr_14",
    "model_score",
    "kelly_pct",
    # Outcome (filled later)
    "horizon_trading_days",
    "next_date",
    "actual_price",
    "return_pct",
    "hit_target",
    "outcome",
]


def _safe_float(x: Any) -> float | None:
    try:
        if x is None:
            return None
        return float(x)
    except Exception:
        return None


def _today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


@dataclass
class PaperTradeRecord:
    date: str
    ticker: str
    signal: str
    ml_confidence: float | None
    regime: str | None
    entry_price: float | None
    target_1: float | None
    hard_stop: float | None
    atr_14: float | None
    model_score: float | None
    kelly_pct: float | None
    horizon_trading_days: int = 20  # ~30 calendar days

    def to_row(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "ticker": self.ticker,
            "signal": self.signal,
            "ml_confidence": self.ml_confidence,
            "regime": self.regime,
            "entry_price": self.entry_price,
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
        }


class PaperTradeLogger:
    def __init__(self, data_root: Path | None = None):
        self.data_root = data_root or _default_data_root()
        self.path = _paper_file(self.data_root)
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
                entry = _safe_float(r.get("close") or r.get("price"))
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

    # ----- Outcomes (backfill) -----

    def _list_eod_dates(self) -> list[str]:
        d = _eod_dir(self.data_root)
        dates: list[str] = []
        for p in d.glob("*.json"):
            try:
                stem = p.stem
                if len(stem) == 10 and stem[4] == "-" and stem[7] == "-":
                    dates.append(stem)
            except Exception:
                pass
        return sorted(dates)

    def _load_snapshot(self, date_str: str) -> dict | None:
        p = _eod_dir(self.data_root) / f"{date_str}.json"
        if not p.exists():
            return None
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

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
            return {"updated": 0, "message": "Need EOD snapshots in backend/data/eod to fill outcomes."}

        idx_by_date = {d: i for i, d in enumerate(dates)}

        updated = 0
        for row in rows[:max_rows]:
            try:
                if row.get("outcome"):
                    continue
                as_of = row.get("date")
                if not as_of or as_of not in idx_by_date:
                    continue
                horizon = int(float(row.get("horizon_trading_days") or 20))
                i = idx_by_date[as_of]
                j = i + horizon
                if j >= len(dates):
                    continue  # not enough future snapshots yet
                next_date = dates[j]

                snap = self._load_snapshot(next_date)
                if not snap:
                    continue
                run_by_ticker = {r.get("ticker"): r for r in (snap.get("run_results") or []) if isinstance(r, dict)}
                t = (row.get("ticker") or "").upper()
                r_next = run_by_ticker.get(t)
                actual = _safe_float((r_next or {}).get("close"))
                entry = _safe_float(row.get("entry_price"))
                if actual is None or entry is None or entry <= 0:
                    continue

                ret_pct = round(100 * (actual - entry) / entry, 2)
                tgt = _safe_float(row.get("target_1"))
                hit = None
                if tgt is not None:
                    hit = 1 if actual >= tgt else 0

                row["next_date"] = next_date
                row["actual_price"] = round(actual, 2)
                row["return_pct"] = ret_pct
                row["hit_target"] = hit
                row["outcome"] = "HIT" if hit == 1 else ("MISS" if hit == 0 else None)
                updated += 1
            except Exception:
                continue

        if updated:
            self._write_all(rows)
        return {"updated": updated, "message": None}

    def get_performance_summary(self, min_completed: int = 60) -> dict[str, Any]:
        rows = self._read_all()
        completed = [r for r in rows if r.get("outcome") in ("HIT", "MISS") and _safe_float(r.get("return_pct")) is not None]
        if len(completed) < min_completed:
            return {
                "status": f"Need more data: {len(completed)}/{min_completed} completed trades",
                "completed": len(completed),
                "min_required": min_completed,
            }

        returns = [float(r["return_pct"]) for r in completed if _safe_float(r.get("return_pct")) is not None]
        hits = [int(float(r["hit_target"])) for r in completed if str(r.get("hit_target") or "").strip() != ""]
        win_rate = round(100 * (sum(hits) / len(hits)), 1) if hits else None
        avg_return = round(sum(returns) / len(returns), 2) if returns else None

        wins = [float(r["return_pct"]) for r in completed if str(r.get("hit_target")) == "1" and _safe_float(r.get("return_pct")) is not None]
        losses = [float(r["return_pct"]) for r in completed if str(r.get("hit_target")) == "0" and _safe_float(r.get("return_pct")) is not None]
        avg_win = round(sum(wins) / len(wins), 2) if wins else None
        avg_loss = round(sum(losses) / len(losses), 2) if losses else None

        return {
            "status": "ok",
            "completed": len(completed),
            "win_rate_pct": win_rate,
            "avg_return_pct": avg_return,
            "avg_win_pct": avg_win,
            "avg_loss_pct": avg_loss,
        }

    def get_recent(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = self._read_all()
        # newest last in file; return newest first
        out = list(reversed(rows))[:limit]
        return out

