"""
Signal audit store — immutable capture of model outputs for forward-tracking pilot.

SQLite file: get_data_root() / "signal_audit.db"
Outcomes (7d/30d) filled in Phase 2 via EOD snapshots (Redis first, then files).

Separate from watchlist/portfolio: only tickers in config/signal_audit_cohort.yaml
are logged when signal_audit.enabled is true.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_SCHEMA_VERSION = 3

# Headline audit win rates = accumulate track (~20d, 4-gate model). Velocity tactical uses 5d rules — keep separate.
_ACCUMULATE_TRACK_WHERE = " AND COALESCE(e.track, 'accumulate') NOT IN ('velocity', 'swing')"
_VELOCITY_TRACK_WHERE = " AND COALESCE(e.track, 'accumulate') = 'velocity'"

_VELOCITY_COLUMNS: list[tuple[str, str]] = [
    ("track", "TEXT DEFAULT 'accumulate'"),
    ("velocity_triggered", "INTEGER"),
    ("velocity_score", "REAL"),
    ("rvol", "REAL"),
    ("bb_pct_b", "REAL"),
    ("velocity_detail_json", "TEXT"),
    ("readiness_tier", "TEXT"),
    ("readiness_score", "REAL"),
    ("tactical_t1", "REAL"),
    ("tactical_t2", "REAL"),
    ("tactical_stop", "REAL"),
    ("horizon_trading_days", "INTEGER DEFAULT 20"),
    # entry_mode: full_go / starter_only / hard_lock — finer-grained than binary go_no_go
    ("entry_mode", "TEXT"),
]

_CREATE_SIGNAL_EVENTS = """
CREATE TABLE IF NOT EXISTS signal_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL,
  signal_date TEXT NOT NULL,
  signal_ts TEXT NOT NULL,
  ticker TEXT NOT NULL,
  sector TEXT,
  market_cap_bucket TEXT,
  cohort_tag TEXT NOT NULL DEFAULT 'audit_100',
  retail_verdict TEXT,
  ml_signal TEXT,
  go_no_go TEXT,
  gates_passed INTEGER,
  gates_total INTEGER DEFAULT 4,
  gate_detail_json TEXT,
  price_at_signal REAL NOT NULL,
  price_source TEXT,
  stop_swing REAL,
  stop_build REAL,
  stop_thesis REAL,
  st_target REAL,
  mt_target REAL,
  lt_target REAL,
  entry_zone_low REAL,
  entry_zone_high REAL,
  composite_score REAL,
  rsi REAL,
  regime_label TEXT,
  hmm_bull_pct REAL,
  market_hmm_bull_pct REAL,
  ml_short_prob REAL,
  ml_medium_prob REAL,
  ml_long_prob REAL,
  confidence_low REAL,
  confidence_high REAL,
  temperature TEXT,
  config_hash TEXT,
  run_source TEXT NOT NULL DEFAULT 'live',
  decision_snapshot TEXT,
  source TEXT NOT NULL DEFAULT 'live',
  UNIQUE(signal_date, ticker, cohort_tag, source)
);
"""

_CREATE_SIGNAL_OUTCOMES = """
CREATE TABLE IF NOT EXISTS signal_outcomes (
  signal_event_id INTEGER PRIMARY KEY REFERENCES signal_events(id),
  resolved_ts TEXT,
  price_7d REAL,
  price_30d REAL,
  return_7d_pct REAL,
  return_30d_pct REAL,
  hit_stop_swing INTEGER,
  hit_st_target INTEGER,
  hit_mt_target INTEGER,
  max_gain_pct REAL,
  max_drawdown_pct REAL,
  path_days INTEGER DEFAULT 30,
  verdict TEXT,
  verdict_rule TEXT,
  benchmark_return_30d_pct REAL,
  notes TEXT
);
"""

_CREATE_META = """
CREATE TABLE IF NOT EXISTS audit_meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
"""

_CREATE_AUDIT_DAILY_SUMMARY = """
CREATE TABLE IF NOT EXISTS audit_daily_summary (
  summary_date TEXT PRIMARY KEY,
  cohort_tag TEXT,
  n_signals INTEGER,
  n_with_outcomes INTEGER,
  payload_json TEXT NOT NULL
);
"""


def _safe_float(x: Any) -> float | None:
    try:
        if x is None:
            return None
        return float(x)
    except Exception:
        return None


def compute_config_hash(config: dict) -> str:
    """Hash score/confidence thresholds for reproducibility."""
    score = config.get("score") or {}
    conf = config.get("confidence") or {}
    payload = {
        "buy_min": score.get("buy_min"),
        "sell_max": score.get("sell_max"),
        "regime_up_min": (config.get("regime") or {}).get("up_min"),
        "regime_down_max": (config.get("regime") or {}).get("down_max"),
        "confidence_action": conf.get("action_thresholds"),
    }
    raw = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _today_est() -> str:
    from signals.time_et import today_est

    return today_est()


def _now_iso() -> str:
    from signals.time_et import now_iso_et

    return now_iso_et()


def _band_high(band: dict | None) -> float | None:
    if not isinstance(band, dict):
        return None
    return _safe_float(band.get("high"))


def _band_low(band: dict | None) -> float | None:
    if not isinstance(band, dict):
        return None
    return _safe_float(band.get("low"))


def _ml_pct(row: dict, key: str) -> float | None:
    v = _safe_float(row.get(key))
    if v is None:
        return None
    if v <= 1.0:
        return round(v * 100.0, 2)
    return round(v, 2)


def _retail_verdict(row: dict) -> str:
    rs = row.get("retail_status") if isinstance(row.get("retail_status"), dict) else {}
    title = rs.get("action_title") or row.get("plan_action") or row.get("signal") or "HOLD"
    return str(title).strip()


def _go_no_go(row: dict) -> str:
    rs = row.get("retail_status") if isinstance(row.get("retail_status"), dict) else {}
    gng = rs.get("go_no_go")
    if gng:
        return str(gng).lower()
    if row.get("gate_cleared") is True:
        return "go"
    if row.get("gate_cleared") is False:
        return "no_go"
    return "mixed"


def _entry_mode(row: dict) -> str | None:
    """Extract entry_mode (full_go / starter_only / hard_lock) from signal row."""
    rs = row.get("retail_status") if isinstance(row.get("retail_status"), dict) else {}
    # retail_action may be nested under retail_status or directly on row
    ra = rs.get("retail_action") or {}
    if isinstance(ra, dict):
        em = ra.get("entry_mode")
        if em in ("full_go", "starter_only", "hard_lock"):
            return em
    # Direct field (set by enrich_dashboard_signal_row)
    em = row.get("entry_mode")
    if em in ("full_go", "starter_only", "hard_lock"):
        return em
    # Derive from go_no_go as fallback for pre-existing rows
    gng = _go_no_go(row)
    if gng == "go":
        return "full_go"
    return None  # can't distinguish starter vs hard_lock without retail_action


def _gates_from_row(row: dict) -> tuple[int, int, str | None]:
    rs = row.get("retail_status") if isinstance(row.get("retail_status"), dict) else {}
    gates = rs.get("gates") or []
    primary_ids = {"valuation", "regime", "momentum", "ml"}
    primary = [g for g in gates if isinstance(g, dict) and g.get("id") in primary_ids]
    if not primary and gates:
        primary = [g for g in gates if isinstance(g, dict)]
    total = len(primary) if primary else 4
    locked = rs.get("gates_locked_count")
    if locked is not None and primary:
        passed = max(0, total - int(locked or 0))
    else:
        passed = sum(1 for g in primary if g.get("pass"))
    detail = json.dumps(gates, default=str) if gates else None
    return passed, total, detail


def _gates_failed_labels(row: dict) -> str | None:
    """Comma-separated primary gate ids that failed (for audit UI/export)."""
    rs = row.get("retail_status") if isinstance(row.get("retail_status"), dict) else {}
    gates = rs.get("gates") or []
    primary_ids = {"valuation", "regime", "momentum", "ml"}
    failed = [
        str(g.get("id"))
        for g in gates
        if isinstance(g, dict) and g.get("id") in primary_ids and not g.get("pass")
    ]
    if not failed and rs.get("gates_locked_count"):
        for g in gates:
            if isinstance(g, dict) and g.get("id") in primary_ids and not g.get("pass"):
                failed.append(str(g.get("id")))
    return ",".join(failed) if failed else None


def _gates_failed_from_json(gate_detail_json: str | None) -> str | None:
    if not gate_detail_json:
        return None
    try:
        gates = json.loads(gate_detail_json)
    except Exception:
        return None
    if not isinstance(gates, list):
        return None
    primary_ids = {"valuation", "regime", "momentum", "ml"}
    failed = [
        str(g.get("id"))
        for g in gates
        if isinstance(g, dict) and g.get("id") in primary_ids and not g.get("pass")
    ]
    return ",".join(failed) if failed else None


def _confidence_band(row: dict) -> tuple[float | None, float | None]:
    conf = _safe_float(row.get("plan_confidence"))
    if conf is None:
        conf = _safe_float(row.get("model_confidence_pct"))
    if conf is None:
        conf = _safe_float(row.get("composite_buy"))
    if conf is None:
        return None, None
    if conf <= 1.0:
        mid = conf * 100.0
    else:
        mid = conf
    # Dashboard rows often expose a point estimate only — use ±4pt band for audit
    return round(max(0.0, mid - 4.0), 1), round(min(100.0, mid + 4.0), 1)


def _temperature_from_regime(regime: str | None) -> str | None:
    if not regime:
        return None
    r = str(regime).upper()
    if r in ("STRONG_BULL", "BULL"):
        return "HOT"
    if r in ("STRONG_BEAR", "BEAR"):
        return "COLD"
    return "NEUTRAL"


def row_to_signal_event(
    row: dict[str, Any],
    *,
    signal_date: str,
    signal_ts: str,
    run_id: str,
    cohort_tag: str,
    market_cap_bucket: str | None,
    config_hash: str,
    run_source: str,
) -> dict[str, Any] | None:
    ticker = str(row.get("ticker") or "").upper().strip()
    if not ticker or row.get("error"):
        return None
    price = _safe_float(row.get("paper_entry_price") or row.get("close") or row.get("price"))
    if price is None or price <= 0:
        return None

    st = row.get("st_band") if isinstance(row.get("st_band"), dict) else {}
    mt = row.get("mt_band") if isinstance(row.get("mt_band"), dict) else {}
    lt = row.get("lt_band") if isinstance(row.get("lt_band"), dict) else {}
    passed, total, gate_json = _gates_from_row(row)
    conf_lo, conf_hi = _confidence_band(row)
    reg = row.get("_global_market_regime") or row.get("regime")

    price_src = None
    if _safe_float(row.get("paper_entry_price")) is not None:
        price_src = str(row.get("paper_entry_source") or "live_quote")
    else:
        price_src = "ohlcv_last_bar"

    snapshot = {
        "signal": row.get("signal"),
        "plan_action": row.get("plan_action"),
        "short_suggestion": row.get("short_suggestion"),
        "medium_suggestion": row.get("medium_suggestion"),
        "long_suggestion": row.get("long_suggestion"),
        "retail_status": row.get("retail_status"),
        "score_label": row.get("score_label"),
        "track": row.get("track"),
        "velocity_reasons": row.get("velocity_reasons"),
    }

    vel_triggered = row.get("velocity_triggered")
    track = str(row.get("track") or ("velocity" if vel_triggered else "accumulate"))
    if vel_triggered is None:
        vel_int = 1 if track == "velocity" else 0
    else:
        vel_int = 1 if bool(vel_triggered) else 0
        if not row.get("track"):
            track = "velocity" if vel_int else "accumulate"
    vel_reasons = row.get("velocity_reasons")
    vel_json = json.dumps(vel_reasons, default=str) if vel_reasons else None

    is_velocity = track == "velocity" or vel_int == 1
    horizon_days = int(row.get("tactical_horizon_trading_days") or row.get("horizon_trading_days") or (5 if is_velocity else 20))
    tactical_t1 = _safe_float(row.get("tactical_t1"))
    tactical_t2 = _safe_float(row.get("tactical_t2"))
    tactical_stop = _safe_float(row.get("tactical_stop"))
    stop_swing = _band_low(st)
    st_target = _band_high(st)
    if is_velocity and tactical_stop is not None:
        stop_swing = tactical_stop
    if is_velocity and tactical_t1 is not None:
        st_target = tactical_t1

    return {
        "run_id": run_id,
        "signal_date": signal_date,
        "signal_ts": signal_ts,
        "ticker": ticker,
        "sector": row.get("sector"),
        "market_cap_bucket": market_cap_bucket,
        "cohort_tag": cohort_tag,
        "retail_verdict": _retail_verdict(row),
        "ml_signal": str(row.get("signal") or ""),
        "go_no_go": _go_no_go(row),
        "gates_passed": passed,
        "gates_total": total,
        "gate_detail_json": gate_json,
        "price_at_signal": round(price, 4),
        "price_source": price_src,
        "stop_swing": stop_swing,
        "stop_build": _band_low(mt),
        "stop_thesis": _band_low(lt),
        "st_target": st_target,
        "mt_target": _band_high(mt) if not is_velocity else tactical_t2,
        "lt_target": _band_high(lt),
        "entry_zone_low": _band_low(st),
        "entry_zone_high": _band_high(st),
        "composite_score": _safe_float(row.get("composite_buy")),
        "rsi": _safe_float(row.get("rsi")),
        "regime_label": str(reg) if reg is not None else None,
        "hmm_bull_pct": _safe_float(row.get("hmm_bull_pct")),
        "market_hmm_bull_pct": None,
        "ml_short_prob": _ml_pct(row, "ml_short_prob"),
        "ml_medium_prob": _ml_pct(row, "ml_medium_prob"),
        "ml_long_prob": _ml_pct(row, "ml_long_prob"),
        "confidence_low": conf_lo,
        "confidence_high": conf_hi,
        "temperature": _temperature_from_regime(str(reg) if reg else None),
        "config_hash": config_hash,
        "run_source": run_source,
        "decision_snapshot": json.dumps(snapshot, default=str),
        "source": "live",
        "track": track,
        "velocity_triggered": vel_int,
        "velocity_score": _safe_float(row.get("velocity_score")),
        "rvol": _safe_float(row.get("rvol")),
        "bb_pct_b": _safe_float(row.get("bb_pct_b")),
        "velocity_detail_json": vel_json,
        "readiness_tier": row.get("readiness_tier"),
        "entry_mode": _entry_mode(row),
        "readiness_score": _safe_float(row.get("readiness_score")),
        "tactical_t1": tactical_t1,
        "tactical_t2": tactical_t2,
        "tactical_stop": tactical_stop,
        "horizon_trading_days": horizon_days,
    }


class SignalAuditStore:
    def __init__(self, data_root: Path | None = None):
        if data_root is None:
            from config_loader import get_data_root

            data_root = get_data_root()
        self.data_root = Path(data_root)
        self.data_root.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data_root / "signal_audit.db"
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(_CREATE_SIGNAL_EVENTS)
            conn.execute(_CREATE_SIGNAL_OUTCOMES)
            conn.execute(_CREATE_META)
            conn.execute(_CREATE_AUDIT_DAILY_SUMMARY)
            self._migrate_columns(conn)
            conn.execute(
                "INSERT OR REPLACE INTO audit_meta(key, value) VALUES (?, ?)",
                ("schema_version", str(_SCHEMA_VERSION)),
            )
            conn.commit()

    def _migrate_columns(self, conn: sqlite3.Connection) -> None:
        existing = {r[1] for r in conn.execute("PRAGMA table_info(signal_events)").fetchall()}
        for col, typ in _VELOCITY_COLUMNS:
            if col not in existing:
                conn.execute(f"ALTER TABLE signal_events ADD COLUMN {col} {typ}")

    def insert_event(self, event: dict[str, Any]) -> tuple[bool, str]:
        """
        Insert one signal event. Returns (inserted, message).
        Idempotent on (signal_date, ticker, cohort_tag, source).
        """
        cols = [
            "run_id",
            "signal_date",
            "signal_ts",
            "ticker",
            "sector",
            "market_cap_bucket",
            "cohort_tag",
            "retail_verdict",
            "ml_signal",
            "go_no_go",
            "gates_passed",
            "gates_total",
            "gate_detail_json",
            "price_at_signal",
            "price_source",
            "stop_swing",
            "stop_build",
            "stop_thesis",
            "st_target",
            "mt_target",
            "lt_target",
            "entry_zone_low",
            "entry_zone_high",
            "composite_score",
            "rsi",
            "regime_label",
            "hmm_bull_pct",
            "market_hmm_bull_pct",
            "ml_short_prob",
            "ml_medium_prob",
            "ml_long_prob",
            "confidence_low",
            "confidence_high",
            "temperature",
            "config_hash",
            "run_source",
            "decision_snapshot",
            "source",
            "track",
            "velocity_triggered",
            "velocity_score",
            "rvol",
            "bb_pct_b",
            "velocity_detail_json",
            "readiness_tier",
            "readiness_score",
            "entry_mode",
            "tactical_t1",
            "tactical_t2",
            "tactical_stop",
            "horizon_trading_days",
        ]
        placeholders = ", ".join("?" for _ in cols)
        col_names = ", ".join(cols)
        values = [event.get(c) for c in cols]
        try:
            with self._connect() as conn:
                conn.execute(
                    f"INSERT INTO signal_events ({col_names}) VALUES ({placeholders})",
                    values,
                )
                conn.commit()
            return True, "inserted"
        except sqlite3.IntegrityError:
            return False, "duplicate"
        except Exception as e:
            logger.debug("signal_audit insert failed: %s", e)
            return False, str(e)

    def count_events(
        self,
        *,
        cohort_tag: str | None = None,
        signal_date: str | None = None,
        since_date: str | None = None,
    ) -> int:
        q = "SELECT COUNT(*) AS n FROM signal_events WHERE source = 'live'"
        params: list[Any] = []
        if cohort_tag:
            q += " AND cohort_tag = ?"
            params.append(cohort_tag)
        if signal_date:
            q += " AND signal_date = ?"
            params.append(signal_date)
        if since_date:
            q += " AND signal_date >= ?"
            params.append(since_date)
        with self._connect() as conn:
            row = conn.execute(q, params).fetchone()
            return int(row["n"]) if row else 0

    def get_pilot_status(self, cohort_tag: str, expected_tickers: int = 100) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                  COUNT(*) AS n_events,
                  COUNT(DISTINCT signal_date) AS n_days,
                  MIN(signal_date) AS first_date,
                  MAX(signal_date) AS last_date
                FROM signal_events
                WHERE cohort_tag = ? AND source = 'live'
                """,
                (cohort_tag,),
            ).fetchone()
        n_events = int(row["n_events"]) if row else 0
        n_days = int(row["n_days"]) if row else 0
        return {
            "cohort_tag": cohort_tag,
            "expected_tickers_per_day": expected_tickers,
            "total_events": n_events,
            "distinct_days": n_days,
            "first_date": row["first_date"] if row else None,
            "last_date": row["last_date"] if row else None,
            "db_path": str(self.db_path),
        }

    def list_records(
        self,
        *,
        cohort_tag: str,
        limit: int = 100,
        signal_date: str | None = None,
        ticker: str | None = None,
    ) -> list[dict[str, Any]]:
        q = """
            SELECT id, signal_date, signal_ts, ticker, market_cap_bucket, retail_verdict, ml_signal,
                   go_no_go, gates_passed, gates_total, price_at_signal, st_target, stop_swing,
                   composite_score, rsi, regime_label, ml_short_prob, confidence_low, confidence_high,
                   run_source
            FROM signal_events
            WHERE cohort_tag = ? AND source = 'live'
        """
        params: list[Any] = [cohort_tag]
        if signal_date:
            q += " AND signal_date = ?"
            params.append(signal_date)
        if ticker:
            q += " AND ticker = ?"
            params.append(str(ticker).upper())
        q += " ORDER BY signal_date DESC, ticker ASC LIMIT ?"
        params.append(max(1, min(limit, 500)))
        with self._connect() as conn:
            rows = conn.execute(q, params).fetchall()
        return [dict(r) for r in rows]

    def breakdown_rows(
        self,
        cohort_tag: str,
        group_col: str,
        *,
        allowed_cols: frozenset[str] | None = None,
        since_date: str | None = None,
    ) -> list[dict[str, Any]]:
        allowed = allowed_cols or frozenset(
            {
                "gates_passed",
                "go_no_go",
                "entry_mode",
                "market_cap_bucket",
                "ml_signal",
                "retail_verdict",
                "regime_label",
                "track",
                "readiness_tier",
                "velocity_triggered",
            }
        )
        if group_col not in allowed:
            return []
        q = f"""
            SELECT {group_col} AS bucket,
                   COUNT(*) AS n,
                   AVG(composite_score) AS avg_score,
                   SUM(CASE WHEN go_no_go = 'go' OR entry_mode IN ('full_go', 'starter_only') THEN 1 ELSE 0 END) AS n_go
            FROM signal_events
            WHERE cohort_tag = ? AND source = 'live'
        """
        params: list[Any] = [cohort_tag]
        if since_date:
            q += " AND signal_date >= ?"
            params.append(since_date)
        q += f"""
            GROUP BY {group_col}
            ORDER BY n DESC
        """
        with self._connect() as conn:
            rows = conn.execute(q, params).fetchall()
        out: list[dict[str, Any]] = []
        for r in rows:
            n = int(r["n"] or 0)
            out.append({
                "bucket": r["bucket"],
                "n": n,
                "avg_score": round(float(r["avg_score"]), 1) if r["avg_score"] is not None else None,
                "go_pct": round(100.0 * int(r["n_go"] or 0) / n, 1) if n else 0.0,
            })
        return out

    def gate_blocker_breakdown(self, cohort_tag: str, *, since_date: str | None = None) -> list[dict[str, Any]]:
        """Count how often each primary gate fails across cohort captures."""
        from collections import Counter

        q = """
            SELECT gate_detail_json FROM signal_events
            WHERE cohort_tag = ? AND source = 'live'
        """
        params: list[Any] = [cohort_tag]
        if since_date:
            q += " AND signal_date >= ?"
            params.append(since_date)
        with self._connect() as conn:
            rows = conn.execute(q, params).fetchall()
        counts: Counter[str] = Counter()
        for r in rows:
            label = _gates_failed_from_json(r["gate_detail_json"])
            if not label:
                continue
            for gid in label.split(","):
                gid = gid.strip()
                if gid:
                    counts[gid] += 1
        n_events = len(rows)
        return [
            {
                "gate": gid,
                "n": n,
                "pct_of_events": round(100.0 * n / n_events, 1) if n_events else 0.0,
            }
            for gid, n in counts.most_common()
        ]

    def gate_pass_rate_breakdown(self, cohort_tag: str, *, since_date: str | None = None) -> list[dict[str, Any]]:
        """Share of captured events where each primary gate passes (not blocking)."""
        from collections import Counter

        primary_ids = ("valuation", "regime", "momentum", "ml")
        q = """
            SELECT gate_detail_json FROM signal_events
            WHERE cohort_tag = ? AND source = 'live'
        """
        params: list[Any] = [cohort_tag]
        if since_date:
            q += " AND signal_date >= ?"
            params.append(since_date)
        with self._connect() as conn:
            rows = conn.execute(q, params).fetchall()
        pass_counts: Counter[str] = Counter()
        for r in rows:
            raw = r["gate_detail_json"]
            if not raw:
                continue
            try:
                gates = json.loads(raw)
            except Exception:
                continue
            if not isinstance(gates, list):
                continue
            for g in gates:
                if not isinstance(g, dict):
                    continue
                gid = str(g.get("id") or "")
                if gid not in primary_ids:
                    continue
                if g.get("pass"):
                    pass_counts[gid] += 1
        n_events = len(rows)
        out: list[dict[str, Any]] = []
        for gid in primary_ids:
            pn = int(pass_counts.get(gid, 0))
            out.append({
                "gate": gid,
                "pass_n": pn,
                "pass_pct": round(100.0 * pn / n_events, 1) if n_events else 0.0,
                "fail_pct": round(100.0 * (n_events - pn) / n_events, 1) if n_events else 0.0,
            })
        out.sort(key=lambda x: x["pass_pct"])
        return out

    def daily_capture_counts(self, cohort_tag: str, limit: int = 30) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT signal_date, COUNT(*) AS n
                FROM signal_events
                WHERE cohort_tag = ? AND source = 'live'
                GROUP BY signal_date
                ORDER BY signal_date DESC
                LIMIT ?
                """,
                (cohort_tag, limit),
            ).fetchall()
        return [{"date": r["signal_date"], "count": int(r["n"])} for r in rows]

    def batch_queue_summary(self, cohort_tag: str, signal_date: str | None = None) -> dict[str, Any]:
        """
        Split last session (or full cohort) into accumulate vs tactical (velocity) queues for Model Audit UI.
        """
        q = """
            SELECT COALESCE(track, 'accumulate') AS track,
                   ticker,
                   velocity_triggered,
                   velocity_score,
                   rvol,
                   bb_pct_b,
                   gates_passed,
                   gates_total,
                   go_no_go,
                   readiness_tier
            FROM signal_events
            WHERE cohort_tag = ? AND source = 'live'
        """
        params: list[Any] = [cohort_tag]
        if signal_date:
            q += " AND signal_date = ?"
            params.append(signal_date)
        q += " ORDER BY ticker ASC"
        with self._connect() as conn:
            rows = conn.execute(q, params).fetchall()

        accumulate: list[dict[str, Any]] = []
        tactical: list[dict[str, Any]] = []
        for r in rows:
            d = dict(r)
            is_tactical = d.get("track") == "velocity" or d.get("velocity_triggered") == 1
            if is_tactical:
                tactical.append(d)
            else:
                accumulate.append(d)

        return {
            "signal_date": signal_date,
            "accumulate_count": len(accumulate),
            "tactical_count": len(tactical),
            "accumulate_tickers": [x["ticker"] for x in accumulate],
            "tactical_tickers": [x["ticker"] for x in tactical],
            "tactical_preview": tactical[:20],
            "accumulate_preview": [
                x for x in accumulate if x.get("readiness_tier") in ("almost_ready", "go_ready")
            ][:20],
        }

    def tickers_on_date(self, cohort_tag: str, signal_date: str) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT ticker FROM signal_events
                WHERE cohort_tag = ? AND signal_date = ? AND source = 'live'
                ORDER BY ticker
                """,
                (cohort_tag, signal_date),
            ).fetchall()
        return [str(r["ticker"]) for r in rows]

    def list_events_for_resolution(self, *, cohort_tag: str, limit: int = 5000) -> list[dict[str, Any]]:
        q = """
            SELECT e.id, e.signal_date, e.ticker, e.retail_verdict, e.ml_signal, e.go_no_go,
                   e.price_at_signal, e.stop_swing, e.st_target, e.mt_target,
                   e.track, e.velocity_triggered, e.horizon_trading_days,
                   e.tactical_t1, e.tactical_t2, e.tactical_stop
            FROM signal_events e
            LEFT JOIN signal_outcomes o ON o.signal_event_id = e.id
            WHERE e.cohort_tag = ? AND e.source = 'live' AND o.signal_event_id IS NULL
            ORDER BY e.signal_date ASC, e.ticker ASC
            LIMIT ?
        """
        with self._connect() as conn:
            rows = conn.execute(q, (cohort_tag, max(1, min(limit, 10000)))).fetchall()
        return [dict(r) for r in rows]

    def has_outcome(self, signal_event_id: int) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM signal_outcomes WHERE signal_event_id = ?",
                (signal_event_id,),
            ).fetchone()
        return row is not None

    def outcome_is_complete(self, signal_event_id: int) -> bool:
        """True when 30d verdict row exists (not partial 7d-only)."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT verdict, return_30d_pct FROM signal_outcomes WHERE signal_event_id = ?",
                (signal_event_id,),
            ).fetchone()
        if not row:
            return False
        return row["verdict"] is not None or row["return_30d_pct"] is not None

    def count_partial_7d_outcomes(self, *, cohort_tag: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS n FROM signal_outcomes o
                JOIN signal_events e ON e.id = o.signal_event_id
                WHERE e.cohort_tag = ? AND e.source = 'live'
                  AND o.return_7d_pct IS NOT NULL
                  AND o.verdict IS NULL
                """,
                (cohort_tag,),
            ).fetchone()
        return int(row["n"] or 0) if row else 0

    def upsert_outcome(self, outcome: dict[str, Any]) -> None:
        cols = [
            "signal_event_id",
            "resolved_ts",
            "price_7d",
            "price_30d",
            "return_7d_pct",
            "return_30d_pct",
            "hit_stop_swing",
            "hit_st_target",
            "hit_mt_target",
            "max_gain_pct",
            "max_drawdown_pct",
            "path_days",
            "verdict",
            "verdict_rule",
            "benchmark_return_30d_pct",
            "notes",
        ]
        placeholders = ", ".join("?" for _ in cols)
        col_names = ", ".join(cols)
        values = [outcome.get(c) for c in cols]
        with self._connect() as conn:
            conn.execute(
                f"""
                INSERT INTO signal_outcomes ({col_names}) VALUES ({placeholders})
                ON CONFLICT(signal_event_id) DO UPDATE SET
                  resolved_ts=excluded.resolved_ts,
                  price_7d=excluded.price_7d,
                  price_30d=excluded.price_30d,
                  return_7d_pct=excluded.return_7d_pct,
                  return_30d_pct=excluded.return_30d_pct,
                  hit_stop_swing=excluded.hit_stop_swing,
                  hit_st_target=excluded.hit_st_target,
                  hit_mt_target=excluded.hit_mt_target,
                  max_gain_pct=excluded.max_gain_pct,
                  max_drawdown_pct=excluded.max_drawdown_pct,
                  path_days=excluded.path_days,
                  verdict=excluded.verdict,
                  verdict_rule=excluded.verdict_rule,
                  benchmark_return_30d_pct=excluded.benchmark_return_30d_pct,
                  notes=excluded.notes
                """,
                values,
            )
            conn.commit()

    def outcome_summary(self, *, cohort_tag: str, since_date: str | None = None) -> dict[str, Any]:
        date_filter = " AND e.signal_date >= ?" if since_date else ""
        params_base: list[Any] = [cohort_tag]
        if since_date:
            params_base.append(since_date)
        with self._connect() as conn:
            total = conn.execute(
                f"""
                SELECT COUNT(*) AS n FROM signal_events e
                WHERE e.cohort_tag = ? AND e.source = 'live'{date_filter}
                """,
                tuple(params_base),
            ).fetchone()
            resolved = conn.execute(
                f"""
                SELECT COUNT(*) AS n FROM signal_outcomes o
                JOIN signal_events e ON e.id = o.signal_event_id
                WHERE e.cohort_tag = ? AND e.source = 'live'{date_filter}
                """,
                tuple(params_base),
            ).fetchone()
            resolved_accumulate = conn.execute(
                f"""
                SELECT COUNT(*) AS n FROM signal_outcomes o
                JOIN signal_events e ON e.id = o.signal_event_id
                WHERE e.cohort_tag = ? AND e.source = 'live'{date_filter}{_ACCUMULATE_TRACK_WHERE}
                """,
                tuple(params_base),
            ).fetchone()
            resolved_velocity = conn.execute(
                f"""
                SELECT COUNT(*) AS n FROM signal_outcomes o
                JOIN signal_events e ON e.id = o.signal_event_id
                WHERE e.cohort_tag = ? AND e.source = 'live'{date_filter}{_VELOCITY_TRACK_WHERE}
                """,
                tuple(params_base),
            ).fetchone()
            _win_breakdown_where = f"{date_filter}{_ACCUMULATE_TRACK_WHERE}"
            by_verdict = conn.execute(
                f"""
                SELECT o.verdict AS bucket, COUNT(*) AS n,
                       AVG(o.return_30d_pct) AS avg_return_30d_pct,
                       AVG(o.return_7d_pct) AS avg_return_7d_pct
                FROM signal_outcomes o
                JOIN signal_events e ON e.id = o.signal_event_id
                WHERE e.cohort_tag = ? AND e.source = 'live' AND o.verdict IS NOT NULL{_win_breakdown_where}
                GROUP BY o.verdict
                ORDER BY n DESC
                """,
                tuple(params_base),
            ).fetchall()
            by_go = conn.execute(
                f"""
                SELECT e.go_no_go AS bucket,
                       COUNT(*) AS n,
                       SUM(CASE WHEN o.verdict = 'WIN' THEN 1 ELSE 0 END) AS n_win,
                       SUM(CASE WHEN o.verdict = 'LOSS' THEN 1 ELSE 0 END) AS n_loss
                FROM signal_outcomes o
                JOIN signal_events e ON e.id = o.signal_event_id
                WHERE e.cohort_tag = ? AND e.source = 'live'{_win_breakdown_where}
                GROUP BY e.go_no_go
                """,
                tuple(params_base),
            ).fetchall()
            by_signal = conn.execute(
                f"""
                SELECT e.ml_signal AS bucket,
                       COUNT(*) AS n,
                       SUM(CASE WHEN o.verdict = 'WIN' THEN 1 ELSE 0 END) AS n_win,
                       SUM(CASE WHEN o.verdict = 'LOSS' THEN 1 ELSE 0 END) AS n_loss
                FROM signal_outcomes o
                JOIN signal_events e ON e.id = o.signal_event_id
                WHERE e.cohort_tag = ? AND e.source = 'live'{_win_breakdown_where}
                GROUP BY e.ml_signal
                ORDER BY n DESC
                LIMIT 12
                """,
                tuple(params_base),
            ).fetchall()
            by_gates = conn.execute(
                f"""
                SELECT e.gates_passed AS bucket,
                       COUNT(*) AS n,
                       SUM(CASE WHEN o.verdict = 'WIN' THEN 1 ELSE 0 END) AS n_win,
                       SUM(CASE WHEN o.verdict = 'LOSS' THEN 1 ELSE 0 END) AS n_loss
                FROM signal_outcomes o
                JOIN signal_events e ON e.id = o.signal_event_id
                WHERE e.cohort_tag = ? AND e.source = 'live'{_win_breakdown_where}
                GROUP BY e.gates_passed
                ORDER BY e.gates_passed DESC
                """,
                tuple(params_base),
            ).fetchall()
            by_entry_mode = conn.execute(
                f"""
                SELECT e.entry_mode AS bucket,
                       COUNT(*) AS n,
                       SUM(CASE WHEN o.verdict = 'WIN' THEN 1 ELSE 0 END) AS n_win,
                       SUM(CASE WHEN o.verdict = 'LOSS' THEN 1 ELSE 0 END) AS n_loss
                FROM signal_outcomes o
                JOIN signal_events e ON e.id = o.signal_event_id
                WHERE e.cohort_tag = ? AND e.source = 'live'{_win_breakdown_where}
                GROUP BY e.entry_mode
                ORDER BY n DESC
                """,
                tuple(params_base),
            ).fetchall()
            by_track = conn.execute(
                f"""
                SELECT e.track AS bucket,
                       COUNT(*) AS n,
                       SUM(CASE WHEN o.verdict = 'WIN' THEN 1 ELSE 0 END) AS n_win,
                       SUM(CASE WHEN o.verdict = 'LOSS' THEN 1 ELSE 0 END) AS n_loss
                FROM signal_outcomes o
                JOIN signal_events e ON e.id = o.signal_event_id
                WHERE e.cohort_tag = ? AND e.source = 'live'{date_filter}
                GROUP BY e.track
                ORDER BY n DESC
                """,
                tuple(params_base),
            ).fetchall()
            by_category = conn.execute(
                f"""
                SELECT e.market_cap_bucket AS bucket,
                       COUNT(*) AS n,
                       SUM(CASE WHEN o.verdict = 'WIN' THEN 1 ELSE 0 END) AS n_win,
                       SUM(CASE WHEN o.verdict = 'LOSS' THEN 1 ELSE 0 END) AS n_loss
                FROM signal_outcomes o
                JOIN signal_events e ON e.id = o.signal_event_id
                WHERE e.cohort_tag = ? AND e.source = 'live'{_win_breakdown_where}
                GROUP BY e.market_cap_bucket
                ORDER BY n DESC
                LIMIT 12
                """,
                tuple(params_base),
            ).fetchall()

            def _slice_stats(extra_where: str = "", extra_params: list[Any] | None = None) -> dict[str, Any]:
                sp = list(params_base) + list(extra_params or [])
                row = conn.execute(
                    f"""
                    SELECT COUNT(*) AS n,
                           SUM(CASE WHEN o.verdict = 'WIN' THEN 1 ELSE 0 END) AS wins,
                           SUM(CASE WHEN o.verdict = 'LOSS' THEN 1 ELSE 0 END) AS losses,
                           SUM(CASE WHEN o.verdict = 'NEUTRAL' THEN 1 ELSE 0 END) AS neutral
                    FROM signal_outcomes o
                    JOIN signal_events e ON e.id = o.signal_event_id
                    WHERE e.cohort_tag = ? AND e.source = 'live'{date_filter}{extra_where}
                    """,
                    tuple(sp),
                ).fetchone()
                n = int(row["n"] or 0)
                wins = int(row["wins"] or 0)
                losses = int(row["losses"] or 0)
                neutral = int(row["neutral"] or 0)
                decided = wins + losses + neutral
                actionable = wins + losses
                return {
                    "n": n,
                    "wins": wins,
                    "losses": losses,
                    "neutral": neutral,
                    "win_rate_pct": round(100.0 * wins / decided, 1) if decided else None,
                    "actionable_win_rate_pct": round(100.0 * wins / actionable, 1) if actionable else None,
                }

            actionable_slices = {
                "full_go": _slice_stats(f" AND e.entry_mode = 'full_go'{_ACCUMULATE_TRACK_WHERE}"),
                "go_4_gates": _slice_stats(
                    f" AND e.gates_passed = 4 AND e.go_no_go = 'go'{_ACCUMULATE_TRACK_WHERE}"
                ),
                "gates_3plus": _slice_stats(f" AND e.gates_passed >= 3{_ACCUMULATE_TRACK_WHERE}"),
                "starter_only": _slice_stats(f" AND e.entry_mode = 'starter_only'{_ACCUMULATE_TRACK_WHERE}"),
                "all_go": _slice_stats(f" AND e.go_no_go = 'go'{_ACCUMULATE_TRACK_WHERE}"),
                "hold_no_go": _slice_stats(f" AND e.go_no_go = 'no_go'{_ACCUMULATE_TRACK_WHERE}"),
                "accumulate_all": _slice_stats(_ACCUMULATE_TRACK_WHERE),
                "velocity_tactical": _slice_stats(_VELOCITY_TRACK_WHERE),
            }

            all_tracks_slice = _slice_stats("")

        n_total = int(total["n"]) if total else 0
        n_resolved = int(resolved["n"]) if resolved else 0
        n_resolved_accumulate = int(resolved_accumulate["n"]) if resolved_accumulate else 0
        n_resolved_velocity = int(resolved_velocity["n"]) if resolved_velocity else 0
        partial_7d = self.count_partial_7d_outcomes(cohort_tag=cohort_tag)
        wins = sum(int(r["n"] or 0) for r in by_verdict if str(r["bucket"]).upper() == "WIN")
        losses = sum(int(r["n"] or 0) for r in by_verdict if str(r["bucket"]).upper() == "LOSS")
        decided = wins + losses + sum(
            int(r["n"] or 0) for r in by_verdict if str(r["bucket"]).upper() == "NEUTRAL"
        )
        accumulate_headline = actionable_slices.get("accumulate_all") or {}
        tactical_summary = actionable_slices.get("velocity_tactical") or {}

        def _win_rate_rows(rows) -> list[dict[str, Any]]:
            out: list[dict[str, Any]] = []
            for r in rows:
                n = int(r["n"] or 0)
                nw = int(r["n_win"] or 0)
                nl = int(r["n_loss"] or 0)
                actionable = nw + nl
                out.append({
                    "bucket": r["bucket"],
                    "n": n,
                    "wins": nw,
                    "losses": nl,
                    "win_rate_pct": round(100.0 * nw / actionable, 1) if actionable else None,
                })
            return out

        verdict_rows = []
        for r in by_verdict:
            n = int(r["n"] or 0)
            verdict_rows.append({
                "bucket": r["bucket"],
                "n": n,
                "avg_return_7d_pct": round(float(r["avg_return_7d_pct"]), 2)
                if r["avg_return_7d_pct"] is not None
                else None,
                "avg_return_30d_pct": round(float(r["avg_return_30d_pct"]), 2)
                if r["avg_return_30d_pct"] is not None
                else None,
            })

        # Fallback chain: prefer the strictest slice with enough resolved rows to be
        # meaningful (n>=5), loosening only when the stricter ones are too thin. The
        # UI must label the headline number by whichever slice actually won this
        # chain — a fixed "4/4 GO or full_go" label is wrong once it falls through
        # to gates_3plus/all_go, which include 3-of-4-gate (or gate-count-agnostic) rows.
        headline_slice_name = "go_4_gates"
        headline_slice = actionable_slices.get("go_4_gates") or {}
        if int(headline_slice.get("n") or 0) < 5:
            headline_slice_name = "full_go"
            headline_slice = actionable_slices.get("full_go") or headline_slice
        if int(headline_slice.get("n") or 0) < 5:
            headline_slice_name = "gates_3plus"
            headline_slice = actionable_slices.get("gates_3plus") or headline_slice
        if int(headline_slice.get("n") or 0) < 5:
            headline_slice_name = "all_go"
            headline_slice = actionable_slices.get("all_go") or headline_slice

        actionable_total = int(accumulate_headline.get("wins") or 0) + int(accumulate_headline.get("losses") or 0)
        accumulate_wins = int(accumulate_headline.get("wins") or 0)
        accumulate_losses = int(accumulate_headline.get("losses") or 0)
        accumulate_neutral = int(accumulate_headline.get("neutral") or 0)
        all_tracks_wins = int(all_tracks_slice.get("wins") or 0)
        all_tracks_losses = int(all_tracks_slice.get("losses") or 0)
        all_tracks_decided = all_tracks_wins + all_tracks_losses + int(all_tracks_slice.get("neutral") or 0)

        return {
            "events_total": n_total,
            "resolved_n": n_resolved,
            "resolved_n_accumulate": n_resolved_accumulate,
            "resolved_n_velocity": n_resolved_velocity,
            "partial_7d_n": partial_7d,
            "pending_n": max(0, n_total - n_resolved),
            "since_date": since_date,
            "track_scope": "accumulate",
            "track_scope_note": "Headline win % excludes velocity tactical (5d rules) — see tactical_summary and by_track.",
            "win_rate_pct": accumulate_headline.get("actionable_win_rate_pct"),
            "blended_win_rate_pct": round(100.0 * all_tracks_wins / all_tracks_decided, 1) if all_tracks_decided else None,
            "all_tracks_actionable_win_rate_pct": all_tracks_slice.get("actionable_win_rate_pct"),
            "wins": accumulate_wins,
            "losses": accumulate_losses,
            "neutral": accumulate_neutral,
            "tactical_summary": tactical_summary if int(tactical_summary.get("n") or 0) > 0 else None,
            "by_verdict": verdict_rows,
            "by_go_no_go": _win_rate_rows(by_go),
            "by_ml_signal": _win_rate_rows(by_signal),
            "by_gates_passed": _win_rate_rows(by_gates),
            "by_entry_mode": _win_rate_rows(by_entry_mode),
            "by_track": _win_rate_rows(by_track),
            "by_category": _win_rate_rows(by_category),
            "actionable_slices": actionable_slices,
            "headline_actionable_win_rate_pct": headline_slice.get("actionable_win_rate_pct"),
            "headline_actionable_n": headline_slice.get("n"),
            # Which slice actually produced the headline number, so the UI doesn't
            # show a fixed "4/4 GO or full_go" label once this has fallen through
            # to a looser slice (gates_3plus / all_go) for lack of resolved rows.
            "headline_actionable_slice": headline_slice_name,
            "headline_actionable_slice_label": {
                "go_4_gates": "4/4 gates + GO",
                "full_go": "full_go",
                "gates_3plus": "≥3/4 gates (fallback — too few 4/4 rows resolved yet)",
                "all_go": "any GO, any gate count (fallback — too few 4/4 rows resolved yet)",
            }[headline_slice_name],
        }

    def list_records_with_outcomes(
        self,
        *,
        cohort_tag: str,
        limit: int = 100,
        offset: int = 0,
        signal_date: str | None = None,
        since_date: str | None = None,
        ticker: str | None = None,
    ) -> list[dict[str, Any]]:
        q = """
            SELECT e.id, e.signal_date, e.signal_ts, e.ticker, e.market_cap_bucket, e.retail_verdict, e.ml_signal,
                   e.go_no_go, e.entry_mode, e.gates_passed, e.gates_total, e.price_at_signal, e.st_target, e.stop_swing, e.mt_target,
                   e.composite_score, e.rsi, e.regime_label, e.temperature, e.ml_short_prob, e.confidence_low,
                   e.confidence_high, e.run_source, e.gate_detail_json,
                   e.track, e.velocity_triggered, e.velocity_score, e.rvol, e.bb_pct_b,
                   e.readiness_tier, e.readiness_score, e.tactical_t1, e.tactical_t2, e.tactical_stop,
                   e.horizon_trading_days,
                   o.return_7d_pct, o.return_30d_pct, o.verdict, o.verdict_rule, o.hit_st_target, o.hit_stop_swing,
                   o.max_gain_pct, o.max_drawdown_pct, o.benchmark_return_30d_pct
            FROM signal_events e
            LEFT JOIN signal_outcomes o ON o.signal_event_id = e.id
            WHERE e.cohort_tag = ? AND e.source = 'live'
        """
        params: list[Any] = [cohort_tag]
        if signal_date:
            q += " AND e.signal_date = ?"
            params.append(signal_date)
        if since_date:
            q += " AND e.signal_date >= ?"
            params.append(since_date)
        if ticker:
            q += " AND e.ticker = ?"
            params.append(str(ticker).upper())
        q += " ORDER BY e.signal_date DESC, e.ticker ASC LIMIT ? OFFSET ?"
        params.append(max(1, min(limit, 10000)))
        params.append(max(0, offset))
        with self._connect() as conn:
            rows = conn.execute(q, params).fetchall()
        out: list[dict[str, Any]] = []
        for r in rows:
            d = dict(r)
            d.pop("gate_detail_json", None)
            d["gates_failed"] = _gates_failed_from_json(r["gate_detail_json"])
            out.append(d)
        return out

    def save_daily_summary(
        self,
        *,
        summary_date: str,
        cohort_tag: str,
        n_signals: int,
        n_with_outcomes: int,
        payload: dict[str, Any],
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO audit_daily_summary (summary_date, cohort_tag, n_signals, n_with_outcomes, payload_json)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(summary_date) DO UPDATE SET
                  cohort_tag=excluded.cohort_tag,
                  n_signals=excluded.n_signals,
                  n_with_outcomes=excluded.n_with_outcomes,
                  payload_json=excluded.payload_json
                """,
                (summary_date, cohort_tag, n_signals, n_with_outcomes, json.dumps(payload, default=str)),
            )
            conn.commit()


def _audit_outcomes_note(
    *,
    eod_snapshots: int,
    has_outcomes: bool,
    partial_7d_n: int,
    progress_days: int,
) -> str | None:
    if has_outcomes and partial_7d_n == 0:
        return None
    parts: list[str] = []
    if eod_snapshots > 0:
        parts.append(f"{eod_snapshots} EOD snapshots on disk")
    if partial_7d_n > 0:
        parts.append(f"{partial_7d_n} rows have 7d return (30d verdict pending)")
    if eod_snapshots < 8:
        parts.append("7d returns need ~8+ snapshots after each signal date")
    if eod_snapshots < 21:
        parts.append("30d verdicts need ~21+ snapshots after each signal date")
    if progress_days < 4:
        parts.append(f"pilot day {progress_days}/30 — keep running run_daily")
    if not parts:
        return "Outcomes resolve after ~20 EOD trading days per signal (7d/20d returns, WIN/LOSS/NEUTRAL)."
    return " · ".join(parts) + "."


def _merge_breakdown_win_rates(
    breakdown: list[dict[str, Any]],
    win_rows: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    if not win_rows:
        return breakdown
    by_bucket = {str(r.get("bucket")): r.get("win_rate_pct") for r in win_rows}
    out: list[dict[str, Any]] = []
    for row in breakdown:
        merged = dict(row)
        merged["win_rate_pct"] = by_bucket.get(str(row.get("bucket")))
        out.append(merged)
    return out


def _retail_gate_thresholds_payload() -> dict[str, float | int]:
    from signals.retail_action_payload import (
        REGIME_GATE,
        ST_ML_GATE,
        VALUATION_GATE_PARTIAL_PCT,
        VALUATION_GATE_PASS_PCT,
    )

    return {
        "regime_bull_pct_min": REGIME_GATE,
        "valuation_full_mos_pct": VALUATION_GATE_PASS_PCT,
        "valuation_partial_mos_pct": VALUATION_GATE_PARTIAL_PCT,
        "ml_short_prob_min": ST_ML_GATE,
        "momentum_rsi_max": 50,
        "momentum_pattern_min": 45,
    }


def _actionable_win_rate(wins: int, losses: int) -> float | None:
    actionable = wins + losses
    return round(100.0 * wins / actionable, 1) if actionable else None


def analyze_buy_win_gap(conn, cohort_tag: str) -> dict[str, Any]:
    """
    Diagnose why ml_signal=BUY win % lags headline actionable win %.
    Accumulate track only; compares full_go vs gate-blocked BUY labels.
    """
    base_where = (
        "e.cohort_tag = ? AND e.source = 'live' AND o.verdict IS NOT NULL"
        f"{_ACCUMULATE_TRACK_WHERE}"
    )
    buy_ml_where = " AND UPPER(TRIM(e.ml_signal)) IN ('BUY', 'STRONG BUY')"

    def _row_stats(extra: str = "", params: tuple[Any, ...] = ()) -> dict[str, Any]:
        row = conn.execute(
            f"""
            SELECT COUNT(*) AS n,
                   SUM(CASE WHEN o.verdict = 'WIN' THEN 1 ELSE 0 END) AS wins,
                   SUM(CASE WHEN o.verdict = 'LOSS' THEN 1 ELSE 0 END) AS losses,
                   SUM(CASE WHEN o.verdict = 'NEUTRAL' THEN 1 ELSE 0 END) AS neutral,
                   AVG(e.composite_score) AS avg_score
            FROM signal_outcomes o
            JOIN signal_events e ON e.id = o.signal_event_id
            WHERE {base_where}{extra}
            """,
            (cohort_tag,) + params,
        ).fetchone()
        n = int(row["n"] or 0)
        wins = int(row["wins"] or 0)
        losses = int(row["losses"] or 0)
        neutral = int(row["neutral"] or 0)
        return {
            "n": n,
            "wins": wins,
            "losses": losses,
            "neutral": neutral,
            "actionable_win_rate_pct": _actionable_win_rate(wins, losses),
            "avg_score": round(float(row["avg_score"]), 1) if row["avg_score"] is not None else None,
        }

    def _group_stats(group_col: str, extra: str = "", limit: int = 12) -> list[dict[str, Any]]:
        rows = conn.execute(
            f"""
            SELECT e.{group_col} AS bucket,
                   COUNT(*) AS n,
                   SUM(CASE WHEN o.verdict = 'WIN' THEN 1 ELSE 0 END) AS wins,
                   SUM(CASE WHEN o.verdict = 'LOSS' THEN 1 ELSE 0 END) AS losses
            FROM signal_outcomes o
            JOIN signal_events e ON e.id = o.signal_event_id
            WHERE {base_where}{buy_ml_where}{extra}
            GROUP BY e.{group_col}
            ORDER BY n DESC
            LIMIT {int(limit)}
            """,
            (cohort_tag,),
        ).fetchall()
        out: list[dict[str, Any]] = []
        for r in rows:
            wins = int(r["wins"] or 0)
            losses = int(r["losses"] or 0)
            out.append({
                "bucket": r["bucket"],
                "n": int(r["n"] or 0),
                "wins": wins,
                "losses": losses,
                "actionable_win_rate_pct": _actionable_win_rate(wins, losses),
            })
        return out

    buy_all = _row_stats(buy_ml_where)
    buy_full_go = _row_stats(buy_ml_where + " AND e.entry_mode = 'full_go'")
    buy_starter = _row_stats(buy_ml_where + " AND e.entry_mode = 'starter_only'")
    buy_hard_lock = _row_stats(buy_ml_where + " AND e.entry_mode = 'hard_lock'")
    buy_go_4 = _row_stats(
        buy_ml_where + " AND e.gates_passed = 4 AND e.go_no_go = 'go'"
    )
    hold_no_go = _row_stats(" AND e.go_no_go = 'no_go' AND UPPER(TRIM(e.ml_signal)) = 'HOLD'")

    loss_rules = conn.execute(
        f"""
        SELECT o.verdict_rule AS bucket,
               COUNT(*) AS n
        FROM signal_outcomes o
        JOIN signal_events e ON e.id = o.signal_event_id
        WHERE {base_where}{buy_ml_where} AND o.verdict = 'LOSS'
        GROUP BY o.verdict_rule
        ORDER BY n DESC
        LIMIT 8
        """,
        (cohort_tag,),
    ).fetchall()

    gate_fail_rows = conn.execute(
        f"""
        SELECT e.gate_detail_json
        FROM signal_outcomes o
        JOIN signal_events e ON e.id = o.signal_event_id
        WHERE {base_where}{buy_ml_where} AND o.verdict = 'LOSS'
        """,
        (cohort_tag,),
    ).fetchall()
    fail_counts: dict[str, int] = {}
    for gr in gate_fail_rows:
        raw = gr["gate_detail_json"]
        if not raw:
            continue
        try:
            gates = json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            continue
        if not isinstance(gates, list):
            continue
        for g in gates:
            if not isinstance(g, dict):
                continue
            gid = str(g.get("id") or "")
            if gid and not g.get("pass"):
                fail_counts[gid] = fail_counts.get(gid, 0) + 1

    top_gate_failures = sorted(
        [{"gate": k, "n": v} for k, v in fail_counts.items()],
        key=lambda x: x["n"],
        reverse=True,
    )[:6]

    recommendations: list[str] = []
    gap_note = (
        "Headline ~75% blends mostly NO-GO/HOLD (caution verdict: win when return ≤0). "
        "BUY uses buy-side rules (+3% or ST target before stop) — harder bar in uptrends."
    )
    if int(buy_all.get("n") or 0) >= 10:
        not_full = int(buy_all.get("n") or 0) - int(buy_full_go.get("n") or 0)
        full_wr = buy_full_go.get("actionable_win_rate_pct")
        all_wr = buy_all.get("actionable_win_rate_pct")
        if not_full > 20 and full_wr is not None and all_wr is not None and full_wr - all_wr >= 15:
            recommendations.append(
                f"BUY without full_go ({not_full} rows) drags ml_signal=BUY win %. "
                f"full_go BUY is {full_wr}% vs all BUY {all_wr}%. "
                "Live UI now downgrades non-full_go BUY to WATCH; headline BUY bucket is legacy-heavy."
            )
        if full_wr is not None and full_wr >= 70:
            recommendations.append(
                f"Actionable BUY (full_go) already at {full_wr}% — target 70% met on entry slice; "
                "improve headline BUY by not treating gate-blocked ML labels as buys."
            )
        elif full_wr is not None and full_wr < 65 and int(buy_full_go.get("n") or 0) >= 15:
            recommendations.append(
                f"Even full_go BUY is {full_wr}% (n={buy_full_go.get('n')}) — tighten ML gate threshold "
                "or require momentum+regime pass before ML can emit BUY (see gate_backtest / backtest_gates.py)."
            )
    for cat in _group_stats("market_cap_bucket"):
        if int(cat.get("n") or 0) >= 25 and cat.get("actionable_win_rate_pct") is not None:
            if cat["actionable_win_rate_pct"] < 55:
                recommendations.append(
                    f"BUY underperforms in {cat['bucket']} ({cat['actionable_win_rate_pct']}% "
                    f"n={cat['n']}) — consider category-specific ML threshold or gate cap."
                )
            elif cat["actionable_win_rate_pct"] >= 75:
                recommendations.append(
                    f"BUY strong in {cat['bucket']} ({cat['actionable_win_rate_pct']}% n={cat['n']})."
                )

    if top_gate_failures:
        top = top_gate_failures[0]
        recommendations.append(
            f"Top failed gate on BUY losses: {top['gate']} ({top['n']} rows) — "
            "many losses may be pre-align BUY rows where gates were not cleared."
        )

    return {
        "methodology_note": gap_note,
        "buy_all": buy_all,
        "buy_full_go": buy_full_go,
        "buy_go_4_gates": buy_go_4,
        "buy_starter_only": buy_starter,
        "buy_hard_lock": buy_hard_lock,
        "hold_no_go_reference": hold_no_go,
        "buy_by_entry_mode": _group_stats("entry_mode"),
        "buy_by_gates_passed": _group_stats("gates_passed"),
        "buy_by_category": _group_stats("market_cap_bucket"),
        "buy_loss_verdict_rules": [
            {"rule": r["bucket"], "n": int(r["n"] or 0)} for r in loss_rules
        ],
        "buy_loss_top_gate_failures": top_gate_failures,
        "recommendations": recommendations[:8],
        "target_win_rate_pct": 70.0,
    }


def build_gate_calibration_guidance(
    *,
    gate_pass_rates: list[dict[str, Any]],
    gate_blockers: list[dict[str, Any]],
    actionable_slices: dict[str, Any] | None,
) -> dict[str, Any]:
    """Evidence-based notes on whether to loosen gate thresholds (defaults: keep valuation strict)."""
    pass_by_gate = {str(g["gate"]): float(g.get("pass_pct") or 0) for g in gate_pass_rates}
    fail_by_gate = {str(b["gate"]): float(b.get("pct_of_events") or 0) for b in gate_blockers}
    val_fail = fail_by_gate.get("valuation", 0.0)
    mom_fail = fail_by_gate.get("momentum", 0.0)
    regime_fail = fail_by_gate.get("regime", 0.0)
    mom_pass = pass_by_gate.get("momentum", 0.0)

    notes: list[str] = []
    if val_fail >= 70:
        notes.append(
            "Valuation blocks most events — expected when spot is rich vs model FV. "
            "Keep 25% MOS for full GO; starter_only (15–25% MOS) is the intended partial path."
        )
    if mom_fail >= 35 and mom_pass < 40:
        notes.append(
            "Momentum (RSI < 50 and pattern ≥ 45) fails often in bull tape. "
            "Review win rate on 3/4-gate rows before raising RSI cap — do not lower valuation MOS."
        )
    if regime_fail >= 40:
        notes.append(
            "Regime gate filters stormy HMM tape. starter_only can still apply when valuation passes "
            "but tech gates fail — loosen regime only if 3/4-gate win rate justifies it."
        )

    full_go = (actionable_slices or {}).get("full_go") or {}
    go_4 = (actionable_slices or {}).get("go_4_gates") or {}
    if int(full_go.get("n") or 0) == 0 and int(go_4.get("n") or 0) == 0:
        notes.append(
            "No resolved full-GO outcomes yet — headline win rate blends mostly HOLD/NO-GO. "
            "Use actionable slice win rate once 4/4 GO rows accumulate."
        )
    vel = (actionable_slices or {}).get("velocity_tactical") or {}
    if int(vel.get("n") or 0) > 0:
        notes.append(
            "Headline win % is accumulate-only (~20d, 4-gate model). "
            f"Velocity tactical (n={vel.get('n')}) uses 5d T+1 rules — see tactical_summary / By track, not blended into headline."
        )

    return {
        "recommend_loosen_valuation": False,
        "recommend_loosen_regime": False,
        "recommend_momentum_review": mom_fail >= 35 and mom_pass < 40,
        "thresholds": _retail_gate_thresholds_payload(),
        "notes": notes,
    }


def build_model_audit_payload(
    config: dict,
    data_root: Path | None = None,
    *,
    resolve_outcomes: bool | None = None,
) -> dict[str, Any]:
    """Analysis-tab payload for the fixed cohort pilot (signal_audit.db)."""
    audit_cfg = config.get("signal_audit") or {}
    if not audit_cfg.get("enabled"):
        return {
            "enabled": False,
            "message": "Signal audit disabled in config (signal_audit.enabled).",
        }

    from config_loader import get_audit_cohort_meta, get_audit_cohort_tag, get_audit_cohort_tickers, load_signal_audit_cohort

    cohort_tickers = get_audit_cohort_tickers(config)
    cohort_tag = get_audit_cohort_tag(config)
    cohort_yaml = load_signal_audit_cohort(config)
    categories = cohort_yaml.get("categories") or {}
    category_sizes = {
        str(k): len(v) if isinstance(v, list) else 0 for k, v in categories.items() if isinstance(categories, dict)
    }

    if not cohort_tickers:
        return {
            "enabled": True,
            "cohort_tag": cohort_tag,
            "cohort_size": 0,
            "message": "Audit cohort list is empty — check config/signal_audit_cohort.yaml.",
        }

    store = SignalAuditStore(data_root=data_root)
    eod_snapshots = 0
    try:
        from signals.paper_trade_logger import PaperTradeLogger

        eod_snapshots = len(PaperTradeLogger(data_root=data_root or store.data_root)._list_eod_dates())
    except Exception:
        pass
    pilot = store.get_pilot_status(cohort_tag, expected_tickers=len(cohort_tickers))
    pilot_target_days = int(audit_cfg.get("pilot_target_days", 30))
    distinct_days = int(pilot.get("distinct_days") or 0)

    last_date = pilot.get("last_date")
    last_session_count = store.count_events(cohort_tag=cohort_tag, signal_date=last_date) if last_date else 0
    captured_on_last = store.tickers_on_date(cohort_tag, last_date) if last_date else []
    missing_on_last = sorted(set(cohort_tickers) - set(captured_on_last)) if last_date else list(cohort_tickers)

    has_outcomes = False
    outcome_summary: dict[str, Any] | None = None
    resolve_result: dict[str, Any] | None = None
    try:
        outcome_summary = store.outcome_summary(cohort_tag=cohort_tag)
        has_outcomes = bool(outcome_summary.get("resolved_n")) or bool(
            outcome_summary.get("partial_7d_n")
        )
    except Exception:
        pass

    if resolve_outcomes if resolve_outcomes is not None else audit_cfg.get("resolve_outcomes_on_read", True):
        try:
            from signals.signal_audit_outcomes import resolve_signal_audit_outcomes

            resolve_result = resolve_signal_audit_outcomes(config, data_root=data_root, cohort_tag=cohort_tag)
            if resolve_result.get("updated"):
                outcome_summary = resolve_result.get("summary") or store.outcome_summary(cohort_tag=cohort_tag)
                has_outcomes = bool(
                    outcome_summary
                    and (
                        outcome_summary.get("resolved_n")
                        or outcome_summary.get("partial_7d_n")
                    )
                )
        except Exception as e:
            logger.debug("signal audit outcome resolve: %s", e)

    message = None
    if distinct_days == 0:
        message = "No audit rows yet — run EOD / run_daily after deploy to populate signal_audit.db."
    elif last_session_count < len(cohort_tickers):
        message = f"Last session captured {last_session_count}/{len(cohort_tickers)} cohort tickers."

    gate_pass_rates = store.gate_pass_rate_breakdown(cohort_tag)
    gate_blocker_breakdown = store.gate_blocker_breakdown(cohort_tag)
    gate_calibration = build_gate_calibration_guidance(
        gate_pass_rates=gate_pass_rates,
        gate_blockers=gate_blocker_breakdown,
        actionable_slices=(outcome_summary or {}).get("actionable_slices"),
    )

    buy_win_gap: dict[str, Any] | None = None
    try:
        with store._connect() as conn:
            buy_win_gap = analyze_buy_win_gap(conn, cohort_tag)
    except Exception as e:
        logger.debug("buy_win_gap analysis: %s", e)

    os = outcome_summary or {}
    breakdown_by_gates = _merge_breakdown_win_rates(
        store.breakdown_rows(cohort_tag, "gates_passed"),
        os.get("by_gates_passed"),
    )
    breakdown_by_entry_mode = _merge_breakdown_win_rates(
        store.breakdown_rows(cohort_tag, "entry_mode"),
        os.get("by_entry_mode"),
    )
    breakdown_by_track = _merge_breakdown_win_rates(
        store.breakdown_rows(cohort_tag, "track"),
        os.get("by_track"),
    )
    breakdown_by_category = _merge_breakdown_win_rates(
        store.breakdown_rows(cohort_tag, "market_cap_bucket"),
        os.get("by_category"),
    )
    breakdown_by_go_no_go = _merge_breakdown_win_rates(
        store.breakdown_rows(cohort_tag, "go_no_go"),
        os.get("by_go_no_go"),
    )
    breakdown_by_signal = _merge_breakdown_win_rates(
        store.breakdown_rows(cohort_tag, "ml_signal"),
        os.get("by_ml_signal"),
    )

    return {
        "enabled": True,
        "cohort_tag": cohort_tag,
        "cohort_size": len(cohort_tickers),
        "pilot_target_days": pilot_target_days,
        "pilot_progress_days": distinct_days,
        "pilot": pilot,
        "category_sizes": category_sizes,
        "last_session": {
            "date": last_date,
            "captured": last_session_count,
            "expected": len(cohort_tickers),
            "missing_tickers": missing_on_last[:25],
            "missing_count": len(missing_on_last),
        },
        "daily_captures": store.daily_capture_counts(cohort_tag, limit=30),
        "breakdown_by_gates": breakdown_by_gates,
        "breakdown_by_go_no_go": breakdown_by_go_no_go,
        "breakdown_by_category": breakdown_by_category,
        "breakdown_by_signal": breakdown_by_signal,
        "breakdown_by_regime": store.breakdown_rows(cohort_tag, "regime_label"),
        "breakdown_by_track": breakdown_by_track,
        "breakdown_by_readiness": store.breakdown_rows(cohort_tag, "readiness_tier"),
        "breakdown_by_entry_mode": breakdown_by_entry_mode,
        "gate_blocker_breakdown": gate_blocker_breakdown,
        "gate_pass_rates": gate_pass_rates,
        "gate_calibration": gate_calibration,
        "buy_win_gap": buy_win_gap,
        "batch_queues": store.batch_queue_summary(cohort_tag, last_date),
        "recent_records": store.list_records_with_outcomes(cohort_tag=cohort_tag, limit=80),
        "eod_snapshot_count": eod_snapshots,
        "outcomes_available": has_outcomes or bool((outcome_summary or {}).get("partial_7d_n")),
        "outcome_summary": outcome_summary,
        "outcome_resolve": resolve_result,
        "outcomes_note": _audit_outcomes_note(
            eod_snapshots=eod_snapshots,
            has_outcomes=has_outcomes,
            partial_7d_n=int((outcome_summary or {}).get("partial_7d_n") or 0),
            progress_days=distinct_days,
        ),
        "message": message,
        "methodology": (
            "Fixed 100-ticker cohort logged once per EOD run (not on dashboard refresh). "
            "Separate from paper trading (~your watchlist/portfolio)."
        ),
        "export_url": "/api/audit/export",
        "report_url": "/api/audit/report",
    }


def log_signal_audit_from_results(
    results: list[dict[str, Any]],
    config: dict,
    *,
    date_str: str | None = None,
    run_source: str = "run_daily",
    data_root: Path | None = None,
) -> dict[str, Any]:
    """
    Log audit rows for audit cohort tickers present in results.
    Does not log watchlist/portfolio tickers outside the cohort.
    """
    audit_cfg = config.get("signal_audit") or {}
    if not audit_cfg.get("enabled"):
        return {"enabled": False, "appended": 0, "skipped": 0, "missing": 0}

    from config_loader import get_audit_cohort_meta, get_audit_cohort_tag, get_audit_cohort_tickers

    cohort = set(get_audit_cohort_tickers(config))
    if not cohort:
        return {"enabled": True, "appended": 0, "skipped": 0, "missing": 0, "error": "empty cohort"}

    if run_source == "dashboard" and not audit_cfg.get("log_on_dashboard", False):
        return {
            "enabled": True,
            "skipped": True,
            "reason": "log_on_dashboard false",
            "run_source": run_source,
            "appended": 0,
            "skipped_duplicate": 0,
            "missing_from_run": len(cohort),
            "cohort_size": len(cohort),
        }

    cohort_tag = get_audit_cohort_tag(config)
    meta = get_audit_cohort_meta(config)
    signal_date = date_str or _today_est()
    signal_ts = _now_iso()
    cfg_hash = compute_config_hash(config)
    run_id = f"{signal_date}:{cfg_hash}:{run_source}"

    store = SignalAuditStore(data_root=data_root)
    by_ticker = {
        str(r.get("ticker") or "").upper(): r
        for r in results
        if isinstance(r, dict) and r.get("ticker") and not r.get("error")
    }

    cohort_size = len(cohort)
    present_in_run = sum(1 for sym in cohort if sym in by_ticker)
    try:
        min_ratio = float(audit_cfg.get("min_cohort_capture_ratio", 0.90))
    except (TypeError, ValueError):
        min_ratio = 0.90
    min_ratio = max(0.0, min(1.0, min_ratio))
    capture_ratio = present_in_run / cohort_size if cohort_size else 0.0
    if capture_ratio < min_ratio:
        return {
            "enabled": True,
            "skipped": True,
            "reason": (
                f"cohort capture {present_in_run}/{cohort_size} "
                f"({capture_ratio:.0%}) below min {min_ratio:.0%}"
            ),
            "run_source": run_source,
            "present_in_run": present_in_run,
            "cohort_size": cohort_size,
            "capture_ratio": round(capture_ratio, 3),
            "appended": 0,
            "skipped_duplicate": 0,
            "missing_from_run": cohort_size - present_in_run,
        }

    appended = 0
    skipped = 0
    missing = 0
    for sym in cohort:
        row = by_ticker.get(sym)
        if not row:
            missing += 1
            continue
        if not isinstance(row.get("retail_status"), dict):
            try:
                from signals.retail_action_payload import enrich_dashboard_signal_row

                enrich_dashboard_signal_row(row)
            except Exception:
                pass
        event = row_to_signal_event(
            row,
            signal_date=signal_date,
            signal_ts=signal_ts,
            run_id=run_id,
            cohort_tag=cohort_tag,
            market_cap_bucket=meta.get(sym),
            config_hash=cfg_hash,
            run_source=run_source,
        )
        if not event:
            missing += 1
            continue
        ok, _msg = store.insert_event(event)
        if ok:
            appended += 1
        else:
            skipped += 1

    status = store.get_pilot_status(cohort_tag, expected_tickers=len(cohort))
    return {
        "enabled": True,
        "date": signal_date,
        "run_source": run_source,
        "cohort_tag": cohort_tag,
        "cohort_size": len(cohort),
        "appended": appended,
        "skipped_duplicate": skipped,
        "missing_from_run": missing,
        "pilot": status,
    }


def persist_daily_signal_logs(
    results: list[dict[str, Any]],
    config: dict,
    *,
    date_str: str | None = None,
    run_source: str = "run_daily",
    data_root: Path | None = None,
) -> dict[str, Any]:
    """
    Phase 0+1: paper_trades.csv append + SQLite signal audit.
    Called from run_daily and dashboard (idempotent).
    """
    out: dict[str, Any] = {"run_source": run_source, "date": date_str or _today_est()}
    audit_cfg = config.get("signal_audit") or {}
    pt_cfg = config.get("paper_trading") or {}

    if run_source == "run_daily" and not audit_cfg.get("log_on_run_daily", True):
        out["signal_audit"] = {"enabled": False, "skipped": "log_on_run_daily false"}
    elif run_source == "dashboard" and not audit_cfg.get("log_on_dashboard", False):
        out["signal_audit"] = {"enabled": False, "skipped": "log_on_dashboard false"}
    else:
        try:
            out["signal_audit"] = log_signal_audit_from_results(
                results,
                config,
                date_str=date_str,
                run_source=run_source,
                data_root=data_root,
            )
        except Exception as e:
            logger.warning("signal_audit log failed: %s", e)
            out["signal_audit"] = {"enabled": True, "error": str(e)}

    try:
        from signals.paper_trade_logger import PaperTradeLogger
        from config_loader import get_dashboard_signal_universe

        if data_root is None:
            from config_loader import get_data_root

            data_root = get_data_root()
        pt_exec = (pt_cfg.get("execution") or {}) if isinstance(pt_cfg, dict) else {}
        pt = PaperTradeLogger(data_root=data_root, execution_cfg=pt_exec)
        paper_universe = set(get_dashboard_signal_universe(config))
        paper_results = [
            r for r in (results or [])
            if isinstance(r, dict) and (r.get("ticker") or "").upper().strip() in paper_universe
        ]
        out["paper_trades"] = pt.log_signals_from_results(
            paper_results,
            date_str=date_str or _today_est(),
            only_actionable=False,
            config=config,
            allowed_tickers=paper_universe,
        )
        out["velocity_paper_trades"] = pt.log_velocity_trades_from_results(
            paper_results,
            date_str=date_str or _today_est(),
            config=config,
            allowed_tickers=paper_universe,
        )
        out["swing_paper_trades"] = pt.log_swing_trades_from_results(
            paper_results,
            date_str=date_str or _today_est(),
            config=config,
            allowed_tickers=paper_universe,
        )
    except Exception as e:
        logger.debug("paper_trades log failed: %s", e)
        out["paper_trades"] = {"error": str(e)}

    return out
