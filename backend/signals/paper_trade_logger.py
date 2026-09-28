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

from signals.model_version import MODEL_VERSION

logger = logging.getLogger(__name__)


def _default_data_root() -> Path:
    from config_loader import get_data_root

    return get_data_root()


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
    "gate_cleared",
    "go_no_go",
    "gates_passed",
    "gates_total",
    "track",
    "reference_entry_price",
    "limit_fill_date",
    "entry_mode",
    # Gate-mode: full_go / starter_only / hard_lock (distinct from entry_mode execution mode)
    "gate_mode",
    # Plan size: 100 full_go, starter_size_pct (default 25) for starter_only
    "size_pct",
    # Which gate/band/regime logic version produced this trade — see signals/model_version.py.
    # Set once at trade-open time (create functions only); never touched by fill/mtm updates,
    # so it stays frozen to whatever was active when the trade opened.
    "model_version",
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


def _provisional_entry_anchor_date(dates: list[str], signal_date: str) -> str | None:
    """
    Best EOD date for marks before next-session fill exists.
    Never returns a date after the latest snapshot (avoids blocking MTM with a future effective_entry_date).
    """
    if not dates:
        return None
    latest = dates[-1]
    anchor = _first_eod_on_or_after(dates, signal_date)
    if anchor is None:
        try:
            sig_ts = pd.Timestamp(signal_date).normalize()
        except Exception:
            return latest
        for d in reversed(dates):
            try:
                if pd.Timestamp(d).normalize() <= sig_ts:
                    return d
            except Exception:
                continue
        return latest
    try:
        if pd.Timestamp(anchor).normalize() > pd.Timestamp(latest).normalize():
            return latest
    except Exception:
        pass
    return anchor


def _prev_eod_date(dates: list[str], before: str) -> str | None:
    """Latest EOD snapshot date strictly before ``before`` (YYYY-MM-DD)."""
    try:
        before_ts = pd.Timestamp(before).normalize()
    except Exception:
        return None
    prev: str | None = None
    for d in dates:
        try:
            if pd.Timestamp(d).normalize() < before_ts:
                prev = d
        except Exception:
            continue
    return prev


def _net_exit_price(close: float, exit_cost_pct: float) -> float:
    return round(float(close) * (1.0 - exit_cost_pct), 4)


def _paper_cfg(config: dict | None) -> dict[str, Any]:
    return (config or {}).get("paper_trading") or {}


def _entry_mode(config: dict | None) -> str:
    mode = str(_paper_cfg(config).get("entry_mode", "limit_touch")).strip().lower()
    return mode if mode in ("limit_touch", "market") else "limit_touch"


def _reference_entry_from_row(r: dict[str, Any], ref_key: str) -> float | None:
    """
    Model reference limit for patient paper entries.

    st_band_low (default for ST audit): ATR/swing stop side of st_band — aligns with
    paper target/stop. Falls back to suggested_buy_price (MA50/MA200 dip) then support_level.

    suggested_buy_price alone: MA50 if price>MA50 else MA200; often null in sell mode.
    Not the same as st_band or horizon entry_zone from ticker detail.
    """
    key = (ref_key or "st_band_low").strip().lower()
    px: float | None = None

    if key in ("st_band_low", "st", "st_preferred"):
        st = r.get("st_band") if isinstance(r.get("st_band"), dict) else {}
        px = _safe_float(st.get("low"))
        if px is None:
            px = _safe_float(r.get("suggested_buy_price"))
        if px is None:
            px = _safe_float(r.get("support_level"))
    elif key == "support_level":
        px = _safe_float(r.get("support_level"))
        if px is None:
            px = _safe_float(r.get("suggested_buy_price"))
    elif key == "suggested_buy_price":
        px = _safe_float(r.get("suggested_buy_price"))
        if px is None:
            st = r.get("st_band") if isinstance(r.get("st_band"), dict) else {}
            px = _safe_float(st.get("low"))
        if px is None:
            px = _safe_float(r.get("support_level"))
    else:
        st = r.get("st_band") if isinstance(r.get("st_band"), dict) else {}
        px = _safe_float(st.get("low"))

    if px is None or px <= 0:
        return None
    # Limit buy reference must be at or below signal-day close when available
    spot = _safe_float(r.get("close") or r.get("price"))
    if spot is not None and px > spot:
        return None
    return round(px, 2)


def _bar_touches_limit(bar: dict[str, Any], limit_px: float) -> bool:
    lo = _safe_float(bar.get("low"))
    if lo is not None and lo <= limit_px:
        return True
    cl = _safe_float(bar.get("close"))
    return cl is not None and cl <= limit_px


def _is_actionable_signal(sig: str) -> bool:
    s = (sig or "").upper()
    return "STRONG BUY" in s or s.strip() == "BUY" or "HOLD/ADD" in s


def _is_paperable_row(row: dict[str, Any], *, require_actionable: bool) -> bool:
    """
    True when the row should enter the paper book.

    Full BUY/STRONG BUY/HOLD-ADD always qualify when require_actionable.
    starter_only rows that were capped to WATCH still qualify via signal_uncapped /
    signal_gate_capped so partial-size starters are not dropped from the track.
    """
    from signals.tracking_gate import _is_starter_only_row

    sig = str(row.get("signal") or row.get("short_suggestion") or "HOLD")
    if not require_actionable:
        return True
    if _is_actionable_signal(sig):
        return True
    if _is_starter_only_row(row):
        uncapped = str(row.get("signal_uncapped") or "").upper()
        if _is_actionable_signal(uncapped):
            return True
        # EOD may only have capped WATCH + entry_mode/signal_gate_capped — still paper.
        return True
    return False


def _paper_size_pct(row: dict[str, Any], config: dict | None) -> int:
    """Plan size for paper PnL weighting: full_go 100, starter_only config default 25."""
    from signals.tracking_gate import _is_starter_only_row, _row_entry_mode

    pt = _paper_cfg(config)
    starter_pct = int(pt.get("starter_size_pct", 25))
    starter_pct = max(1, min(100, starter_pct))
    em = _row_entry_mode(row)
    if em == "full_go" or (row.get("gate_cleared") is True and em != "starter_only"):
        return 100
    if _is_starter_only_row(row) or em == "starter_only":
        raw = row.get("max_sizing_pct")
        try:
            if raw is not None:
                return max(1, min(100, int(float(raw))))
        except (TypeError, ValueError):
            pass
        return starter_pct
    return 100


def _result_to_paper_record(
    r: dict[str, Any],
    date_str: str,
    horizon_trading_days: int = 20,
    *,
    track: str = "accumulate",
) -> dict[str, Any] | None:
    """Build a paper trade CSV row from one run_signals / EOD run_results dict."""
    t = (r.get("ticker") or "").upper().strip()
    if not t or r.get("error"):
        return None
    sig = r.get("signal") or r.get("short_suggestion") or "HOLD"
    st = r.get("st_band") if isinstance(r.get("st_band"), dict) else None
    target_1 = _safe_float(st.get("high")) if st else None
    hard_stop = _safe_float(st.get("low")) if st else None
    if track == "velocity":
        target_1 = _safe_float(r.get("tactical_t1")) or target_1
        hard_stop = _safe_float(r.get("tactical_stop")) or hard_stop
        horizon_trading_days = int(
            r.get("tactical_horizon_trading_days") or horizon_trading_days
        )
    elif track == "swing":
        target_1 = _safe_float(r.get("swing_t1")) or target_1
        hard_stop = _safe_float(r.get("swing_stop")) or hard_stop
        horizon_trading_days = int(
            r.get("swing_horizon_trading_days") or horizon_trading_days
        )
    ml = r.get("ml_short_prob")
    ml_conf = round(float(ml) * 100, 1) if _safe_float(ml) is not None else None
    reg = r.get("_global_market_regime") or r.get("regime")
    # Swing entries fill at the setup's own anchor (MA21 / resistance / EMA8 / recent low —
    # whichever the stop/target/R:R were actually measured from), not spot/close — the
    # classifier can trigger before price has reached that anchor.
    swing_anchor = _safe_float(r.get("swing_entry_anchor")) if track == "swing" else None
    entry = _safe_float(
        swing_anchor or r.get("paper_entry_price") or r.get("close") or r.get("price")
    )
    entry_src = None
    if swing_anchor is not None:
        entry_src = "swing_entry_anchor"
    elif _safe_float(r.get("paper_entry_price")) is not None:
        entry_src = str(r.get("paper_entry_source") or "live_quote")
    elif entry is not None:
        entry_src = "ohlcv_last_bar"

    # Target must be ABOVE entry for a long trade — if inverted (e.g. T1 tier stored as
    # target on a velocity trade entered above the tier), null it out so fill_outcomes
    # falls back to the return-direction criterion (return > 0 = HIT).
    if target_1 is not None and entry is not None and target_1 <= entry:
        target_1 = None
    # Hard stop must be BELOW entry.
    if hard_stop is not None and entry is not None and hard_stop >= entry:
        hard_stop = None

    atr_14 = _safe_float(r.get("atr_14"))
    score = _safe_float(r.get("composite_buy"))
    from signals.tracking_gate import gate_snapshot_from_row

    gate = gate_snapshot_from_row(r)
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
    row = rec.to_row()
    for k in ("gate_cleared", "go_no_go", "gates_passed", "gates_total"):
        v = gate.get(k)
        if v is not None:
            row[k] = v
    row["track"] = track
    row["model_version"] = r.get("model_version") or MODEL_VERSION
    if track in ("velocity", "swing"):
        row["entry_mode"] = "market"
        if entry is not None:
            row["reference_entry_price"] = round(entry, 2)
    # Gate-level entry mode (full_go / starter_only / hard_lock) — different from the
    # execution entry_mode (limit_touch / market).  Sourced from enrich_dashboard_signal_row.
    gm = r.get("entry_mode")
    if gm in ("full_go", "starter_only", "hard_lock"):
        row["gate_mode"] = gm
    # size_pct set by callers that have config; default full until enriched
    if row.get("size_pct") is None:
        if gm == "starter_only":
            row["size_pct"] = 25
        elif gm == "full_go":
            row["size_pct"] = 100
    return row


def _result_to_velocity_paper_record(
    r: dict[str, Any],
    date_str: str,
    config: dict | None = None,
) -> dict[str, Any] | None:
    """Tactical paper row — velocity triggered; gates logged but not required."""
    if not r.get("velocity_triggered"):
        return None
    vt = (config or {}).get("velocity_tactical") or {}
    horizon = int(vt.get("horizon_trading_days", 5))
    return _result_to_paper_record(r, date_str, horizon_trading_days=horizon, track="velocity")


def _result_to_swing_paper_record(
    r: dict[str, Any],
    date_str: str,
    config: dict | None = None,
) -> dict[str, Any] | None:
    """Swing paper row — swing_triggered; 4-gate GO not required."""
    if not r.get("swing_triggered"):
        return None
    st_cfg = (config or {}).get("swing_tactical") or {}
    horizon = int(r.get("swing_horizon_trading_days") or 12)
    rec = _result_to_paper_record(r, date_str, horizon_trading_days=horizon, track="swing")
    if rec is None:
        return None
    setup = str(r.get("swing_setup_label") or r.get("swing_setup_type") or "swing")
    rec["signal"] = f"SWING:{setup}"
    if r.get("swing_setup_type"):
        rec["swing_setup_type"] = r.get("swing_setup_type")
    if r.get("swing_score") is not None:
        rec["swing_score"] = r.get("swing_score")
    return rec


def _build_limit_paper_row(
    r: dict[str, Any],
    signal_date: str,
    fill_date: str,
    reference_entry: float,
    horizon_trading_days: int,
    entry_cost_pct: float,
) -> dict[str, Any] | None:
    """Paper row after limit order fills at reference entry on fill_date."""
    row = _result_to_paper_record(r, signal_date, horizon_trading_days)
    if row is None:
        return None
    limit_px = round(reference_entry, 2)
    eff = round(limit_px * (1.0 + entry_cost_pct), 4)
    row["entry_mode"] = "limit_touch"
    row["reference_entry_price"] = limit_px
    row["limit_fill_date"] = fill_date
    row["entry_price"] = limit_px
    row["entry_price_source"] = "limit_touch"
    row["effective_entry_date"] = fill_date
    row["effective_entry_price"] = eff
    row["effective_entry_source"] = "limit_touch"
    row["execution_mode"] = "close_to_close"
    return row


def _is_buy_side_signal(sig: str) -> bool:
    """STRONG BUY / BUY / HOLD/ADD — for actionable performance slice (excludes TRIM/REDUCE/WATCH/HOLD)."""
    s = (sig or "").upper()
    if any(x in s for x in ("TRIM", "SELL", "REDUCE", "AVOID")):
        return False
    if s.strip() in ("HOLD", "WATCH"):
        return False
    return "STRONG BUY" in s or s.strip() == "BUY" or "HOLD/ADD" in s


def _is_bearish_signal(sig: str) -> bool:
    s = (sig or "").upper()
    return any(x in s for x in ("TRIM", "SELL", "REDUCE", "AVOID"))


def _velocity_eligible_for_paper(r: dict[str, Any], config: dict | None) -> bool:
    """
    Velocity paper rows are long-only tactical entries — skip bearish signals and optional gate floor.
    """
    vt = (config or {}).get("velocity_tactical") or {}
    sig = str(r.get("signal") or r.get("short_suggestion") or "")
    if vt.get("require_buy_side_for_paper", True) and _is_bearish_signal(sig):
        return False
    min_gates = vt.get("min_gates_for_paper")
    if min_gates is None:
        min_gates = vt.get("tactical_min_gates_for_alert", 0)
    try:
        min_gates = int(min_gates or 0)
    except (TypeError, ValueError):
        min_gates = 0
    if min_gates > 0:
        gp = r.get("gates_passed")
        if gp is not None and int(gp) < min_gates:
            return False
    return True


def _pair_has_new_price_bar(
    row_start: dict[str, Any] | None,
    row_end: dict[str, Any] | None,
    *,
    prior_close: float | None,
    actual_close: float | None,
) -> bool:
    """
    True when the forward window includes a new OHLCV session (not a holiday duplicate snapshot).
    """
    if prior_close is None or actual_close is None:
        return False
    if float(prior_close) != float(actual_close):
        return True
    if not row_start or not row_end:
        return False
    d0 = str(row_start.get("ohlcv_last_date") or "")[:10]
    d1 = str(row_end.get("ohlcv_last_date") or "")[:10]
    if d0 and d1 and d0 != d1:
        return True
    return False


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
    def _dedupe_key(row: dict[str, Any]) -> tuple[str, str, str, str]:
        return (
            str(row.get("date") or ""),
            str(row.get("ticker") or ""),
            str(row.get("track") or "accumulate"),
            str(row.get("signal") or ""),
        )

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
        """Append a signal row (legacy PaperTradeRecord API)."""
        return self.log_signal_row(rec.to_row())

    def log_signal_row(self, row: dict[str, Any]) -> bool:
        """
        Append a signal row.
        Idempotent per (date, ticker, signal) to avoid duplicates on dashboard refresh.
        Returns True if appended, False if skipped.
        """
        rows = self._read_all()
        key = self._dedupe_key(row)
        existing = {self._dedupe_key(r) for r in rows}
        if key in existing:
            return False
        self._ensure_trade_id(row)
        rows.append(row)
        self._write_all(rows)
        return True

    def _ticker_bar_on_snapshot(self, date_str: str, ticker: str) -> dict[str, Any] | None:
        snap = self._load_snapshot(date_str)
        if not snap:
            return None
        row = _run_results_by_ticker_upper(snap.get("run_results") or []).get(ticker.upper())
        if not row:
            return None
        return {
            "close": _safe_float(row.get("close")),
            "high": _safe_float(row.get("high")),
            "low": _safe_float(row.get("low")),
        }

    def _find_limit_fill_date(
        self,
        signal_date: str,
        ticker: str,
        limit_px: float,
        dates: list[str],
        max_wait_bd: int,
    ) -> str | None:
        try:
            sig_ts = pd.Timestamp(signal_date).normalize()
            deadline = sig_ts + BDay(max_wait_bd)
        except Exception:
            return None
        for d in dates:
            try:
                d_ts = pd.Timestamp(d).normalize()
            except Exception:
                continue
            if d_ts < sig_ts:
                continue
            if d_ts > deadline:
                break
            bar = self._ticker_bar_on_snapshot(d, ticker)
            if bar and _bar_touches_limit(bar, limit_px):
                return d
        return None

    def _log_market_signals_from_results(
        self,
        results: list[dict[str, Any]],
        date_str: str,
        horizon_trading_days: int,
        only_actionable: bool,
        config: dict | None,
    ) -> dict[str, Any]:
        from signals.tracking_gate import enrich_tracking_row, passes_tracking_gate

        n_appended = 0
        n_seen = 0
        n_skipped_gate = 0
        for r in results or []:
            try:
                if not isinstance(r, dict):
                    continue
                enrich_tracking_row(r)
                if not passes_tracking_gate(r, config, "paper_trading"):
                    n_skipped_gate += 1
                    continue
                if only_actionable and not _is_paperable_row(r, require_actionable=True):
                    continue
                row = _result_to_paper_record(r, date_str, horizon_trading_days)
                if row is None:
                    continue
                row["entry_mode"] = "market"
                row["size_pct"] = _paper_size_pct(r, config)
                if str(row.get("gate_mode") or "") == "starter_only":
                    row["signal"] = f"STARTER:{r.get('signal_uncapped') or 'BUY'}"
                n_seen += 1
                if self.log_signal_row(row):
                    n_appended += 1
            except Exception:
                continue
        return {
            "date": date_str,
            "seen": n_seen,
            "appended": n_appended,
            "skipped_gate": n_skipped_gate,
            "entry_mode": "market",
        }

    def scan_limit_entries_from_eod(
        self,
        allowed_tickers: set[str] | frozenset[str] | None = None,
        max_signal_days: int = 90,
        horizon_trading_days: int = 20,
        config: dict | None = None,
        live_signal_date: str | None = None,
        live_results: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """
        Patient entries: log a row only when price touches the model reference limit
        within max_wait business days after a GO-gated signal day.
        """
        from signals.tracking_gate import enrich_tracking_row, passes_tracking_gate

        pt_cfg = _paper_cfg(config)
        ref_key = str(pt_cfg.get("reference_entry", "st_band_low"))
        max_wait = int(pt_cfg.get("limit_max_wait_days", 10))
        require_actionable = bool(pt_cfg.get("require_actionable_signal", True))
        entry_cost = self.cost_per_side_pct

        dates = self._list_eod_dates()
        if not dates and not live_results:
            return {
                "appended": 0,
                "signals_scanned": 0,
                "skipped_gate": 0,
                "skipped_no_reference": 0,
                "skipped_no_fill": 0,
                "entry_mode": "limit_touch",
                "message": "No EOD snapshots in Redis or data/eod.",
            }

        scan = dates[-max_signal_days:] if len(dates) > max_signal_days else list(dates)
        rows = self._read_all()
        existing = {self._dedupe_key(r) for r in rows}
        appended = 0
        signals_scanned = 0
        skipped_gate = 0
        skipped_no_ref = 0
        skipped_no_fill = 0

        live_date = live_signal_date or _today_str()
        live_by_ticker = {
            str(r.get("ticker") or "").upper(): r
            for r in (live_results or [])
            if isinstance(r, dict) and r.get("ticker")
        }

        for signal_date in scan:
            snap = self._load_snapshot(signal_date)
            run_results = list((snap or {}).get("run_results") or [])
            if signal_date == live_date and live_by_ticker:
                seen = {str(r.get("ticker") or "").upper() for r in run_results if r.get("ticker")}
                for t, lr in live_by_ticker.items():
                    if t not in seen:
                        run_results.append(lr)

            for r in run_results:
                try:
                    if not isinstance(r, dict):
                        continue
                    t = (r.get("ticker") or "").upper().strip()
                    if not t or r.get("error"):
                        continue
                    if allowed_tickers is not None and t not in allowed_tickers:
                        continue
                    row_copy = dict(r)
                    enrich_tracking_row(row_copy)
                    if not passes_tracking_gate(row_copy, config, "paper_trading"):
                        skipped_gate += 1
                        continue
                    if require_actionable and not _is_paperable_row(
                        row_copy, require_actionable=True
                    ):
                        continue
                    signals_scanned += 1
                    ref_px = _reference_entry_from_row(row_copy, ref_key)
                    if ref_px is None:
                        skipped_no_ref += 1
                        continue
                    fill_date = self._find_limit_fill_date(signal_date, t, ref_px, dates, max_wait)
                    if fill_date is None and signal_date == live_date:
                        bar = {
                            "close": _safe_float(row_copy.get("close") or row_copy.get("price")),
                            "high": _safe_float(row_copy.get("high")),
                            "low": _safe_float(row_copy.get("low")),
                        }
                        if _bar_touches_limit(bar, ref_px):
                            fill_date = live_date
                    if fill_date is None:
                        skipped_no_fill += 1
                        continue
                    rec_row = _build_limit_paper_row(
                        row_copy,
                        signal_date,
                        fill_date,
                        ref_px,
                        horizon_trading_days,
                        entry_cost,
                    )
                    if rec_row is None:
                        continue
                    rec_row["size_pct"] = _paper_size_pct(row_copy, config)
                    # Keep display signal as logged; annotate starter plan for the book.
                    if str(rec_row.get("gate_mode") or "") == "starter_only":
                        rec_row["signal"] = (
                            f"STARTER:{row_copy.get('signal_uncapped') or 'BUY'}"
                        )
                    key = self._dedupe_key(rec_row)
                    if key in existing:
                        continue
                    rows.append(rec_row)
                    existing.add(key)
                    appended += 1
                except Exception:
                    continue

        if appended:
            self._write_all(rows)
        return {
            "appended": appended,
            "signals_scanned": signals_scanned,
            "skipped_gate": skipped_gate,
            "skipped_no_reference": skipped_no_ref,
            "skipped_no_fill": skipped_no_fill,
            "eod_dates_total": len(dates),
            "entry_mode": "limit_touch",
            "message": None,
        }

    def log_signals_from_results(
        self,
        results: list[dict[str, Any]],
        date_str: str | None = None,
        horizon_trading_days: int = 20,
        only_actionable: bool = False,
        config: dict | None = None,
        allowed_tickers: set[str] | frozenset[str] | None = None,
    ) -> dict[str, Any]:
        """
        Log paper trades from run_signals output.
        Default entry_mode=limit_touch scans EOD for GO signals that fill at reference entry.
        """
        date_str = date_str or _today_str()
        pt_cfg = _paper_cfg(config)
        if _entry_mode(config) == "market":
            return self._log_market_signals_from_results(
                results, date_str, horizon_trading_days, only_actionable, config
            )
        max_days = int(pt_cfg.get("backfill_from_eod_days", 90))
        out = self.scan_limit_entries_from_eod(
            allowed_tickers=allowed_tickers,
            max_signal_days=max_days,
            horizon_trading_days=horizon_trading_days,
            config=config,
            live_signal_date=date_str,
            live_results=results,
        )
        out["date"] = date_str
        return out

    def log_velocity_trades_from_results(
        self,
        results: list[dict[str, Any]],
        date_str: str | None = None,
        config: dict | None = None,
        allowed_tickers: set[str] | frozenset[str] | None = None,
    ) -> dict[str, Any]:
        """
        Log tactical paper rows for velocity_triggered names (market close entry).
        Does not require GO gates — gates still recorded on the row.
        """
        vt_cfg = (config or {}).get("velocity_tactical") or {}
        if not vt_cfg.get("enabled", True) or not vt_cfg.get("log_paper_trades", True):
            return {"appended": 0, "skipped": 0, "enabled": False}

        date_str = date_str or _today_str()
        rows = self._read_all()
        existing = {self._dedupe_key(r) for r in rows}

        # Velocity-specific dedup: same (ticker, entry_price) within a 3-day window
        # prevents the same breakout being re-logged on consecutive daily runs while
        # the velocity_triggered flag stays True in the EOD snapshot.
        _vel_window_days = int((vt_cfg.get("dedup_window_days") or 3))
        try:
            from datetime import date as _date, timedelta as _td
            _cutoff = (
                _date.fromisoformat(date_str) - _td(days=_vel_window_days)
            ).isoformat()
        except Exception:
            _cutoff = ""
        _recent_vel: set[tuple[str, str]] = set()
        for _r in rows:
            if str(_r.get("track") or "") == "velocity" and str(_r.get("date") or "") >= _cutoff:
                _ep = str(_r.get("entry_price") or "")
                _tk = str(_r.get("ticker") or "").upper()
                if _tk and _ep:
                    _recent_vel.add((_tk, _ep))

        appended = 0
        skipped = 0

        for r in results or []:
            try:
                if not isinstance(r, dict) or r.get("error"):
                    continue
                t = (r.get("ticker") or "").upper().strip()
                if not t or not r.get("velocity_triggered"):
                    continue
                if not _velocity_eligible_for_paper(r, config):
                    skipped += 1
                    continue
                if allowed_tickers is not None and t not in allowed_tickers:
                    continue
                rec = _result_to_velocity_paper_record(r, date_str, config)
                if rec is None:
                    continue
                rec["entry_mode"] = "market"
                rec["entry_price_source"] = rec.get("entry_price_source") or "ohlcv_last_bar"
                # Standard date/signal dedup
                key = self._dedupe_key(rec)
                if key in existing:
                    skipped += 1
                    continue
                # Rolling window dedup by (ticker, entry_price)
                vel_key = (t, str(rec.get("entry_price") or ""))
                if vel_key in _recent_vel:
                    skipped += 1
                    continue
                rows.append(rec)
                existing.add(key)
                _recent_vel.add(vel_key)
                appended += 1
            except Exception:
                continue

        if appended:
            self._write_all(rows)
        return {"appended": appended, "skipped": skipped, "date": date_str, "track": "velocity"}

    def log_swing_trades_from_results(
        self,
        results: list[dict[str, Any]],
        date_str: str | None = None,
        config: dict | None = None,
        allowed_tickers: set[str] | frozenset[str] | None = None,
    ) -> dict[str, Any]:
        """
        Log swing paper rows for swing_triggered names (market close entry).
        Does not require GO gates — gates still recorded on the row.
        """
        st_cfg = (config or {}).get("swing_tactical") or {}
        if not st_cfg.get("enabled", True) or not st_cfg.get("log_paper_trades", False):
            return {"appended": 0, "skipped": 0, "enabled": False}

        date_str = date_str or _today_str()
        rows = self._read_all()
        existing = {self._dedupe_key(r) for r in rows}

        _window_days = int((st_cfg.get("dedup_window_days") or 5))
        try:
            from datetime import date as _date, timedelta as _td

            _cutoff = (_date.fromisoformat(date_str) - _td(days=_window_days)).isoformat()
        except Exception:
            _cutoff = ""
        _recent_swing: set[tuple[str, str]] = set()
        for _r in rows:
            if str(_r.get("track") or "") == "swing" and str(_r.get("date") or "") >= _cutoff:
                _ep = str(_r.get("entry_price") or "")
                _tk = str(_r.get("ticker") or "").upper()
                if _tk and _ep:
                    _recent_swing.add((_tk, _ep))

        appended = 0
        skipped = 0

        for r in results or []:
            try:
                if not isinstance(r, dict) or r.get("error"):
                    continue
                t = (r.get("ticker") or "").upper().strip()
                if not t or not r.get("swing_triggered"):
                    continue
                if allowed_tickers is not None and t not in allowed_tickers:
                    continue
                rec = _result_to_swing_paper_record(r, date_str, config)
                if rec is None:
                    continue
                rec["entry_mode"] = "market"
                rec["entry_price_source"] = rec.get("entry_price_source") or "ohlcv_last_bar"
                key = self._dedupe_key(rec)
                if key in existing:
                    skipped += 1
                    continue
                swing_key = (t, str(rec.get("entry_price") or ""))
                if swing_key in _recent_swing:
                    skipped += 1
                    continue
                rows.append(rec)
                existing.add(key)
                _recent_swing.add(swing_key)
                appended += 1
            except Exception:
                continue

        if appended:
            self._write_all(rows)
        return {"appended": appended, "skipped": skipped, "date": date_str, "track": "swing"}

    def backfill_from_eod_snapshots(
        self,
        allowed_tickers: set[str] | frozenset[str] | None = None,
        max_days: int = 90,
        horizon_trading_days: int = 20,
        config: dict | None = None,
    ) -> dict[str, Any]:
        """
        Rebuild missing paper trade rows from historical EOD snapshots.
        limit_touch: only rows where reference entry was touched within wait window.
        market: legacy one-row-per-GO-day at close.
        """
        if _entry_mode(config) == "market":
            return self._backfill_market_from_eod(
                allowed_tickers=allowed_tickers,
                max_days=max_days,
                horizon_trading_days=horizon_trading_days,
                config=config,
            )
        return self.scan_limit_entries_from_eod(
            allowed_tickers=allowed_tickers,
            max_signal_days=max_days,
            horizon_trading_days=horizon_trading_days,
            config=config,
        )

    def _backfill_market_from_eod(
        self,
        allowed_tickers: set[str] | frozenset[str] | None = None,
        max_days: int = 90,
        horizon_trading_days: int = 20,
        config: dict | None = None,
    ) -> dict[str, Any]:
        from signals.tracking_gate import enrich_tracking_row, passes_tracking_gate

        dates = self._list_eod_dates()
        if not dates:
            return {
                "appended": 0,
                "dates_scanned": 0,
                "skipped_existing": 0,
                "skipped_gate": 0,
                "entry_mode": "market",
                "message": "No EOD snapshots in Redis or data/eod.",
            }

        scan = dates[-max_days:] if len(dates) > max_days else dates
        rows = self._read_all()
        existing = {self._dedupe_key(r) for r in rows}
        appended = 0
        skipped = 0
        skipped_gate = 0
        dates_scanned = 0

        for date_str in scan:
            snap = self._load_snapshot(date_str)
            if not snap:
                continue
            dates_scanned += 1
            for r in snap.get("run_results") or []:
                try:
                    if not isinstance(r, dict):
                        continue
                    t = (r.get("ticker") or "").upper().strip()
                    if not t or r.get("error"):
                        continue
                    if allowed_tickers is not None and t not in allowed_tickers:
                        continue
                    row_copy = dict(r)
                    enrich_tracking_row(row_copy)
                    if not passes_tracking_gate(row_copy, config, "paper_trading"):
                        skipped_gate += 1
                        continue
                    rec_row = _result_to_paper_record(row_copy, date_str, horizon_trading_days)
                    if rec_row is None:
                        continue
                    rec_row["entry_mode"] = "market"
                    key = self._dedupe_key(rec_row)
                    if key in existing:
                        skipped += 1
                        continue
                    rows.append(rec_row)
                    existing.add(key)
                    appended += 1
                except Exception:
                    continue

        if appended:
            self._write_all(rows)
        return {
            "appended": appended,
            "dates_scanned": dates_scanned,
            "skipped_existing": skipped,
            "skipped_gate": skipped_gate,
            "eod_dates_total": len(dates),
            "entry_mode": "market",
            "message": None,
        }

    @staticmethod
    def _open_rows_for_update(rows: list[dict[str, Any]], max_rows: int = 5000) -> list[dict[str, Any]]:
        """Open trades oldest-first so horizon fills are not starved by rows[:max_rows] on large CSVs."""
        open_rows = [r for r in rows if not r.get("outcome")]
        open_rows.sort(key=lambda r: str(r.get("date") or ""))
        return open_rows[:max_rows]

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

        next_session: use next business day's EOD close when available; until then anchor
        marks to the latest on/after signal date (provisional) so MTM is not blank on weekends.
        """
        mode = self._row_mode(row)
        signal_date = str(row.get("date") or "")
        entry_cost = self._row_cost_pct(row, "entry_cost_pct")
        src = str(row.get("effective_entry_source") or "").strip()

        if src == "limit_touch":
            eff = _safe_float(row.get("effective_entry_price"))
            eff_date = str(row.get("effective_entry_date") or row.get("limit_fill_date") or "").strip() or None
            if eff is not None and eff > 0 and eff_date:
                return eff, eff_date

        eff = _safe_float(row.get("effective_entry_price"))
        eff_date = str(row.get("effective_entry_date") or "").strip() or None
        if eff is not None and eff > 0 and eff_date:
            if mode != "next_session" or src == "next_session_close":
                return eff, eff_date
            # Provisional next_session row — retry when a newer EOD snapshot may exist.

        base_px = None
        base_date = None
        base_src = None

        if mode == "next_session":
            try:
                target_ts = pd.Timestamp(signal_date).normalize() + BDay(1)
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
                if mode == "next_session":
                    base_date = _provisional_entry_anchor_date(dates, signal_date) or signal_date
                    base_src = "signal_entry_provisional"
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
        for row in self._open_rows_for_update(rows, max_rows):
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

    def fill_outcomes(self, max_rows: int = 5000) -> dict[str, Any]:
        """
        Backfill outcomes using EOD snapshots (no extra API calls).
        Uses horizon_trading_days to find the next snapshot date.

        Velocity track rows with outcomes are also re-evaluated: the win/loss criterion
        changed from target-touch to return > 0, so old misclassified outcomes are reset
        and re-resolved on this run.
        """
        rows = self._read_all()
        if not rows:
            return {"updated": 0, "message": "No paper trades logged yet."}

        dates = self._list_eod_dates()
        if len(dates) < 2:
            return {"updated": 0, "message": "Need at least 2 EOD snapshots (Redis or data/eod) to fill outcomes."}

        # Reset outcomes for velocity rows that were classified with the old (inverted-target)
        # logic: those have hit_target=1 but avg_return negative, or target_1 ≤ entry_price.
        reclassified = 0
        for row in rows:
            if str(row.get("track") or "") != "velocity":
                continue
            if not row.get("outcome"):
                continue
            # Re-check: if stored target_1 ≤ entry_price → old inverted-target outcome; reset.
            tgt = _safe_float(row.get("target_1"))
            ent = _safe_float(row.get("entry_price"))
            ret = _safe_float(row.get("return_pct"))
            if tgt is not None and ent is not None and tgt <= ent:
                # Target was below entry — outcome was mis-classified; reset for re-resolution.
                for _f in ("outcome", "hit_target", "hit_stop", "next_date",
                           "actual_price", "actual_price_net", "return_pct"):
                    row[_f] = None
                reclassified += 1
            elif ret is not None:
                # Even if target looks ok: re-verify outcome matches return direction.
                oc = str(row.get("outcome") or "").upper()
                ht = _safe_float(row.get("hit_target"))
                expected_hit = 1 if ret >= 0 else 0
                if ht is not None and int(ht) != expected_hit:
                    for _f in ("outcome", "hit_target", "hit_stop"):
                        row[_f] = None
                    reclassified += 1

        updated = 0
        entry_synced = 0
        for row in self._open_rows_for_update(rows, max_rows):
            try:
                if row.get("outcome"):
                    continue
                as_of = row.get("date")
                if not as_of:
                    continue
                before_entry = (
                    row.get("effective_entry_date"),
                    row.get("effective_entry_source"),
                    row.get("effective_entry_price"),
                )
                eff_entry, eff_entry_date = self._ensure_effective_entry(row, dates)
                after_entry = (
                    row.get("effective_entry_date"),
                    row.get("effective_entry_source"),
                    row.get("effective_entry_price"),
                )
                if after_entry != before_entry:
                    entry_synced += 1
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

                snap_start = self._load_snapshot(str(eff_entry_date or as_of))
                r_start = None
                if snap_start:
                    r_start = _run_results_by_ticker_upper(snap_start.get("run_results") or []).get(t)
                prior_close = _safe_float((r_start or {}).get("close")) or _safe_float(row.get("entry_price"))
                if not _pair_has_new_price_bar(
                    r_start,
                    r_next,
                    prior_close=prior_close,
                    actual_close=actual,
                ):
                    continue

                exit_cost = self._row_cost_pct(row, "exit_cost_pct")
                actual_net = round(float(actual) * (1.0 - exit_cost), 4)
                from signals.stock_splits import cumulative_split_factor

                entry_date = str(eff_entry_date or as_of)[:10]
                sf = cumulative_split_factor(t, entry_date, str(next_date)[:10])
                adj_entry = round(eff_entry * sf, 4) if sf != 1.0 else eff_entry
                ret_pct = round(100 * (actual_net - adj_entry) / adj_entry, 2)
                tgt = _safe_float(row.get("target_1"))
                stop = _safe_float(row.get("hard_stop"))
                if sf != 1.0:
                    if tgt is not None:
                        tgt = round(tgt * sf, 4)
                    if stop is not None:
                        stop = round(stop * sf, 4)
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

                is_velocity = str(row.get("track") or "").lower() == "velocity"
                if is_velocity:
                    # Velocity T+N: win = positive return at horizon; no stop-hit scoring
                    # since the hold-to-horizon design doesn't use intraday stop triggers.
                    outcome = "HIT" if ret_pct >= 0 else "MISS"
                    hit_target = 1 if ret_pct >= 0 else 0
                    hit_stop = None
                elif hit_stop == 1:
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

        if updated or entry_synced or reclassified:
            self._write_all(rows)
        return {"updated": updated, "entry_synced": entry_synced, "reclassified": reclassified, "message": None}

    def mark_to_market(self, max_rows: int = 5000) -> dict[str, Any]:
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
        entry_synced = 0

        for row in self._open_rows_for_update(rows, max_rows):
            try:
                if row.get("outcome"):
                    continue
                self._ensure_trade_id(row)
                before_entry = (
                    row.get("effective_entry_date"),
                    row.get("effective_entry_source"),
                    row.get("effective_entry_price"),
                )
                eff_entry, _eff_date = self._ensure_effective_entry(row, dates)
                if (
                    row.get("effective_entry_date"),
                    row.get("effective_entry_source"),
                    row.get("effective_entry_price"),
                ) != before_entry:
                    entry_synced += 1
                if eff_entry is None or eff_entry <= 0:
                    continue
                t = (row.get("ticker") or "").upper()
                r_now = run_by_ticker.get(t)
                px = _safe_float((r_now or {}).get("close"))
                if px is None:
                    continue
                exit_cost = self._row_cost_pct(row, "exit_cost_pct")
                px_net = _net_exit_price(float(px), exit_cost)
                mtm_ret = round(100 * (px_net - eff_entry) / eff_entry, 2)
                # Daily Δ: prior EOD net mark vs today's net mark (not dependent on prior MTM run).
                prev_eod = _prev_eod_date(dates, latest)
                prev_mark: float | None = None
                eff_date = str(row.get("effective_entry_date") or row.get("date") or "")
                if prev_eod:
                    prev_close = self._ticker_close_on_snapshot(prev_eod, t)
                    if prev_close is not None and prev_close > 0:
                        try:
                            if eff_date and pd.Timestamp(prev_eod).normalize() >= pd.Timestamp(eff_date).normalize():
                                prev_mark = _net_exit_price(float(prev_close), exit_cost)
                        except Exception:
                            prev_mark = _net_exit_price(float(prev_close), exit_cost)
                if prev_mark is None and eff_entry and eff_entry > 0:
                    stored = _safe_float(row.get("rolling_entry_price"))
                    if stored is not None and stored > 0 and str(row.get("mtm_date") or "") != latest:
                        prev_mark = stored
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

        if updated or entry_synced:
            self._write_all(rows)
        return {"updated": updated, "entry_synced": entry_synced, "message": None, "as_of": latest}

    def append_mtm_history(self, max_rows: int = 5000) -> dict[str, Any]:
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
            for row in self._open_rows_for_update(rows, max_rows):
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
                        "total_return_pct": _safe_float(row.get("mtm_return_pct")),
                        "total_pnl_per_share": (
                            round(_safe_float(row.get("mtm_price_net")) - _safe_float(row.get("effective_entry_price")), 4)
                            if _safe_float(row.get("mtm_price_net")) is not None and _safe_float(row.get("effective_entry_price")) is not None
                            else None
                        ),
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

    def sync_mtm_history_from_eod(self, max_rows: int = 5000, max_days: int = 120) -> dict[str, Any]:
        """
        Backfill paper_trades_mtm.jsonl with total P&L % vs entry for each EOD date after entry.
        Each point is cumulative return from effective entry (not daily delta).
        """
        rows = self._read_all()
        if not rows:
            return {"appended": 0, "message": "No paper trades logged yet."}

        dates = self._list_eod_dates()
        if len(dates) < 2:
            return {"appended": 0, "message": "Need at least 2 EOD snapshots."}

        scan = dates[-max_days:] if len(dates) > max_days else dates
        out_path = _mtm_history_file(self.data_root)
        existing_keys: set[str] = set()
        if out_path.exists():
            try:
                with open(out_path, "r", encoding="utf-8") as f:
                    for line in f:
                        try:
                            obj = json.loads(line)
                            tid = str(obj.get("trade_id") or "")
                            d = str(obj.get("mtm_date") or "")
                            if tid and d:
                                existing_keys.add(f"{tid}:{d}")
                        except Exception:
                            continue
            except Exception:
                pass

        appended = 0
        with open(out_path, "a", encoding="utf-8") as f:
            for row in self._open_rows_for_update(rows, max_rows):
                try:
                    self._ensure_trade_id(row)
                    tid = str(row.get("trade_id") or "")
                    eff_entry, eff_entry_date = self._ensure_effective_entry(row, dates)
                    if eff_entry is None or not eff_entry_date or eff_entry <= 0:
                        continue
                    t = (row.get("ticker") or "").upper()
                    exit_cost = self._row_cost_pct(row, "exit_cost_pct")
                    end_date = str(row.get("next_date") or dates[-1])
                    try:
                        end_ts = pd.Timestamp(end_date).normalize()
                    except Exception:
                        end_ts = pd.Timestamp(dates[-1]).normalize()
                    try:
                        start_ts = pd.Timestamp(eff_entry_date).normalize()
                    except Exception:
                        continue
                    for d in scan:
                        try:
                            d_ts = pd.Timestamp(d).normalize()
                        except Exception:
                            continue
                        if d_ts < start_ts or d_ts > end_ts:
                            continue
                        key = f"{tid}:{d}"
                        if key in existing_keys:
                            continue
                        px = self._ticker_close_on_snapshot(d, t)
                        if px is None or px <= 0:
                            continue
                        px_net = _net_exit_price(float(px), exit_cost)
                        total_ret = round(100 * (px_net - eff_entry) / eff_entry, 2)
                        total_pnl = round(px_net - eff_entry, 4)
                        payload = {
                            "trade_id": tid,
                            "trade_date": row.get("date"),
                            "ticker": t,
                            "signal": row.get("signal"),
                            "mtm_date": d,
                            "mtm_price": round(float(px), 2),
                            "mtm_return_pct": total_ret,
                            "total_return_pct": total_ret,
                            "total_pnl_per_share": total_pnl,
                        }
                        f.write(json.dumps(payload) + "\n")
                        existing_keys.add(key)
                        appended += 1
                except Exception:
                    continue
        return {"appended": appended, "message": None}

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
                                "mtm_return_pct": _safe_float(obj.get("total_return_pct") or obj.get("mtm_return_pct")),
                                "mtm_price": _safe_float(obj.get("mtm_price")),
                                "total_pnl_per_share": _safe_float(obj.get("total_pnl_per_share")),
                            }
                        )
                    except Exception:
                        continue
            for tid in list(out.keys()):
                out[tid] = out[tid][-limit_per_trade:]
            return out
        except Exception:
            return {}

    def get_completed_equity_curve(self, max_points: int = 400) -> list[dict[str, Any]]:
        """
        Cumulative pseudo-equity curve from completed paper trades (chronological by exit/next_date).
        Starts at index 100; each trade multiplies by (1 + return_pct/100). Used for public track-record chart.
        """
        rows = self._read_all()
        completed = [
            r
            for r in rows
            if r.get("outcome") in ("HIT", "MISS", "STOP_HIT") and _safe_float(r.get("return_pct")) is not None
        ]
        if not completed:
            return []

        def _exit_date(r: dict[str, Any]) -> str:
            return str(r.get("next_date") or r.get("date") or "")

        completed.sort(key=_exit_date)
        curve: list[dict[str, Any]] = []
        equity = 100.0
        for i, r in enumerate(completed):
            rp = _safe_float(r.get("return_pct"))
            if rp is None:
                continue
            ret = float(rp)
            equity *= 1.0 + ret / 100.0
            curve.append(
                {
                    "date": _exit_date(r),
                    "ticker": (str(r.get("ticker") or "")).upper(),
                    "signal": str(r.get("signal") or ""),
                    "outcome": str(r.get("outcome") or ""),
                    "return_pct": round(ret, 2),
                    "equity_index": round(equity, 4),
                    "cumulative_return_pct": round(equity - 100.0, 2),
                    "trade_n": i + 1,
                }
            )
        return curve[-max_points:]

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

        # Gate-mode breakdown: full_go vs starter_only vs hard_lock
        _gm_stats: dict[str, dict[str, Any]] = {}
        for gm in ("full_go", "starter_only", "hard_lock"):
            gm_rows = [r for r in completed if r.get("gate_mode") == gm]
            if not gm_rows:
                continue
            gm_rets = [float(r["return_pct"]) for r in gm_rows if _safe_float(r.get("return_pct")) is not None]
            gm_hits = [int(float(r.get("hit_target") or 0)) for r in gm_rows if str(r.get("hit_target") or "") != ""]
            _gm_stats[gm] = {
                "n": len(gm_rows),
                "win_rate_pct": round(100 * sum(gm_hits) / len(gm_hits), 1) if gm_hits else None,
                "avg_return_pct": round(sum(gm_rets) / len(gm_rets), 2) if gm_rets else None,
            }
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
        out: dict[str, Any] = {
            "completed_n": len(completed),
            "win_rate_pct": win_rate,
            "avg_return_pct": avg_return,
            "avg_win_pct": avg_win,
            "avg_loss_pct": avg_loss,
            "avg_excess_vs_spy_pct": avg_excess,
            "n_with_benchmark": len(excesses),
        }
        if _gm_stats:
            out["by_gate_mode"] = _gm_stats
        return out

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
        open_rows = [r for r in rows if not r.get("outcome")]
        open_n = len(open_rows)
        open_dates = [str(r.get("date")) for r in open_rows if r.get("date")]
        oldest_open = min(open_dates) if open_dates else None
        eod_n = len(self._list_eod_dates())

        horizon_note = (
            "Completed trades: exit = first EOD on or after entry date + N business days "
            "(per-row horizon_trading_days, default 20). Compare to SPY over the same dates."
        )

        out: dict[str, Any] = {
            "horizon_note": horizon_note,
            "benchmark_ticker": benchmark.upper(),
            "min_required": min_completed,
            "completed": len(completed),
            "open": open_n,
            "total_rows": len(rows),
            "oldest_open_date": oldest_open,
            "eod_snapshots": eod_n,
            "current_model_version": MODEL_VERSION,
        }

        # Need enough rows for basic stats; cap at 5 for default (60) runs, allow 3 when caller passes min_completed=3 (e.g. paper vs forward drift).
        stats_floor = max(3, min(5, int(min_completed)))
        if len(completed) < stats_floor:
            out["status"] = f"Need more data: {len(completed)}/{min_completed} completed trades"
            if open_n:
                hint = (
                    f"{open_n} open ({len(rows)} logged"
                    + (f", oldest open {oldest_open}" if oldest_open else "")
                    + "). "
                )
                if len(rows) <= open_n and eod_n >= 25:
                    hint += (
                        "EOD history exists but paper_trades.csv may be new — refresh Analysis to backfill from EOD. "
                    )
                hint += (
                    "Return/Last mark update daily from EOD; "
                    "final HIT/MISS after entry date + horizon_trading_days (default 20 business days)."
                )
                out["message"] = hint
            else:
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

        accumulate = [
            r
            for r in completed
            if str(r.get("track") or "accumulate") not in ("velocity", "swing")
        ]
        tactical = [r for r in completed if str(r.get("track") or "") == "velocity"]
        swing_track = [r for r in completed if str(r.get("track") or "") == "swing"]

        # Headline win rate must reflect genuinely gate-cleared conviction, not a blend
        # diluted by starter_only (partial-size) rows — paper_trading.log_starter_only
        # deliberately admits those into the same "accumulate" track for data-completeness
        # (see by_gate_mode below), but forward-tracking's own gate-count-vs-win-rate curve
        # shows lower-gate cohorts underperform materially, so blending them into "the"
        # number understated what a fully gate-cleared entry actually does (reported case:
        # 212 of ~237 accumulate rows were starter_only, headline read 34.9% instead of the
        # full_go cohort's real rate). accumulate_go is a stricter subset of accumulate, not
        # a different admission path — nothing about what gets logged changes here.
        accumulate_go = [r for r in accumulate if str(r.get("gate_mode") or "") == "full_go"]

        out["blended_summary"] = {
            "completed_n": stats["completed_n"],
            "win_rate_pct": stats["win_rate_pct"],
            "avg_return_pct": stats["avg_return_pct"],
            "label": "All tracks blended",
        }

        # Headline stats = full_go accumulate (genuinely 4-gate-cleared) when enough data;
        # never blend velocity, swing, or starter_only partial-conviction rows into it.
        headline_floor = max(3, min(5, int(min_actionable)))
        if len(accumulate_go) >= headline_floor:
            headline_stats = self._stats_for_completed(accumulate_go, benchmark)
            out["headline_track"] = "accumulate_go"
        elif len(accumulate) >= headline_floor:
            # Not enough full_go history yet — fall back to the broader accumulate cohort
            # (still excludes velocity/swing) rather than block the headline entirely.
            headline_stats = self._stats_for_completed(accumulate, benchmark)
            out["headline_track"] = "accumulate"
            fallback_note = (
                f"Full-gate (full_go) cohort n={len(accumulate_go)} is too thin yet — "
                f"headline blends in starter_only rows (n={len(accumulate)} total). "
                "See by_gate_mode for the full_go-only read."
            )
            out["message"] = fallback_note if not out.get("message") else f"{out['message']} {fallback_note}"
        elif len(accumulate) > 0:
            headline_stats = self._stats_for_completed(accumulate, benchmark)
            out["headline_track"] = "accumulate_thin"
            thin_note = (
                f"Accumulate track n={len(accumulate)} — preview only; "
                "see tactical breakdown for velocity T+5."
            )
            out["message"] = thin_note if not out.get("message") else f"{out['message']} {thin_note}"
        else:
            headline_stats = {
                "completed_n": 0,
                "win_rate_pct": None,
                "avg_return_pct": None,
                "avg_win_pct": None,
                "avg_loss_pct": None,
                "avg_excess_vs_spy_pct": None,
                "n_with_benchmark": 0,
            }
            out["headline_track"] = "no_accumulate"
            if tactical:
                tac_note = (
                    "Headline win rate is accumulate (4-gate GO) only — "
                    f"velocity tactical has n={len(tactical)} (see breakdown below). "
                    "Not comparable to model audit ~51%."
                )
                out["message"] = tac_note if not out.get("message") else f"{out['message']} {tac_note}"

        out["win_rate_pct"] = headline_stats.get("win_rate_pct")
        out["avg_return_pct"] = headline_stats.get("avg_return_pct")
        out["avg_win_pct"] = headline_stats.get("avg_win_pct")
        out["avg_loss_pct"] = headline_stats.get("avg_loss_pct")
        out["avg_excess_vs_spy_pct"] = headline_stats.get("avg_excess_vs_spy_pct")
        out["n_benchmarked"] = headline_stats.get("n_with_benchmark")

        if buy_stats:
            out["buy_signals_summary"] = {
                "completed_n": buy_stats["completed_n"],
                "win_rate_pct": buy_stats["win_rate_pct"],
                "avg_return_pct": buy_stats["avg_return_pct"],
                "avg_excess_vs_spy_pct": buy_stats["avg_excess_vs_spy_pct"],
                "label": buy_stats["label"],
            }

        if accumulate:
            acc_stats = self._stats_for_completed(accumulate, benchmark)
            out["accumulate_summary"] = {
                "completed_n": acc_stats["completed_n"],
                "win_rate_pct": acc_stats["win_rate_pct"],
                "avg_return_pct": acc_stats["avg_return_pct"],
                "label": "Accumulate track (4-gate GO / swing)",
            }
        if tactical:
            tac_stats = self._stats_for_completed(tactical, benchmark)
            out["tactical_summary"] = {
                "completed_n": tac_stats["completed_n"],
                "win_rate_pct": tac_stats["win_rate_pct"],
                "avg_return_pct": tac_stats["avg_return_pct"],
                "label": "Tactical velocity track (T+5)",
            }
        if swing_track:
            sw_stats = self._stats_for_completed(swing_track, benchmark)
            out["swing_summary"] = {
                "completed_n": sw_stats["completed_n"],
                "win_rate_pct": sw_stats["win_rate_pct"],
                "avg_return_pct": sw_stats["avg_return_pct"],
                "label": "Swing classifier track (T1/stop/time)",
            }

        # Gate-mode tiered breakdown (full_go vs starter_only vs hard_lock)
        # Only meaningful for accumulate track where gates apply.
        if stats.get("by_gate_mode"):
            out["by_gate_mode"] = stats["by_gate_mode"]

        # Per model-version breakdown so Analysis can isolate current logic vs legacy.
        by_mv: dict[str, dict[str, Any]] = {}
        for r in completed:
            bucket = str(r.get("model_version") or "").strip() or "legacy"
            by_mv.setdefault(bucket, []).append(r)
        out["summary_by_model_version"] = {
            ver: {
                "completed_n": s["completed_n"],
                "win_rate_pct": s["win_rate_pct"],
                "avg_return_pct": s["avg_return_pct"],
                "avg_excess_vs_spy_pct": s["avg_excess_vs_spy_pct"],
            }
            for ver, ver_rows in sorted(by_mv.items(), reverse=True)
            for s in [self._stats_for_completed(ver_rows, benchmark)]
        }
        out["current_model_version"] = MODEL_VERSION

        out["marketing_note"] = (
            "Headline marketing stats use the full_go (fully gate-cleared) accumulate "
            "cohort only; starter_only partial-conviction rows, velocity, and swing tracks "
            "are labeled separately, not blended into the headline number."
        )

        return out

    @staticmethod
    def _coerce_numeric_fields(row: dict[str, Any]) -> dict[str, Any]:
        """CSV roundtrip turns None → '' ; coerce back so JSON has null, not '0' in JS."""
        _NUMERIC_KEYS = frozenset({
            "ml_confidence", "entry_price", "effective_entry_price", "reference_entry_price",
            "entry_cost_pct", "exit_cost_pct",
            "target_1", "hard_stop", "atr_14", "model_score", "kelly_pct",
            "actual_price", "actual_price_net", "return_pct",
            "mtm_price", "mtm_price_net", "mtm_return_pct",
            "rolling_entry_price", "rolling_pnl", "rolling_return_pct",
            "benchmark_return_pct", "excess_return_pct",
        })
        for k in _NUMERIC_KEYS:
            v = row.get(k)
            if v is None:
                continue
            if isinstance(v, str):
                v = v.strip()
                if v == "" or v.lower() == "none":
                    row[k] = None
                    continue
            f = _safe_float(v)
            row[k] = f
        return row

    def get_recent(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = self._read_all()
        for row in rows:
            self._ensure_trade_id(row)
            self._coerce_numeric_fields(row)
            # Predating model_version stamps → "legacy" so UI version filter is stable.
            mv = str(row.get("model_version") or "").strip()
            row["model_version"] = mv or "legacy"
        # newest last in file; return newest first
        out = list(reversed(rows))[:limit]
        return out

    def purge_velocity_track(self, *, dry_run: bool = False) -> dict[str, Any]:
        """
        Remove all velocity-track rows from paper_trades.csv.
        Safe to call after the target-inversion and dedup bugs were fixed (Jun 2026).
        Accumulate-track rows are untouched — they were not affected by those bugs.

        dry_run=True reports counts without writing.
        """
        rows = self._read_all()
        velocity = [r for r in rows if str(r.get("track") or "") == "velocity"]
        kept = [r for r in rows if str(r.get("track") or "") != "velocity"]
        if not dry_run and velocity:
            self._write_all(kept)
        return {
            "purged_n": len(velocity),
            "kept_n": len(kept),
            "dry_run": dry_run,
            "message": (
                f"Removed {len(velocity)} velocity-track rows; {len(kept)} accumulate rows kept."
                if not dry_run
                else f"Dry-run: would remove {len(velocity)} velocity rows, keep {len(kept)}."
            ),
        }

