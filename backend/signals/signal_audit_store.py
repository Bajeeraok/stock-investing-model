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

_SCHEMA_VERSION = 1

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
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")
    except Exception:
        return datetime.now().strftime("%Y-%m-%d")


def _now_iso() -> str:
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo("America/New_York")).isoformat(timespec="seconds")
    except Exception:
        return datetime.now().isoformat(timespec="seconds")


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


def _gates_from_row(row: dict) -> tuple[int, int, str | None]:
    rs = row.get("retail_status") if isinstance(row.get("retail_status"), dict) else {}
    gates = rs.get("gates") or []
    primary_ids = {"valuation", "regime", "momentum", "ml"}
    primary = [g for g in gates if isinstance(g, dict) and g.get("id") in primary_ids]
    if not primary and gates:
        primary = [g for g in gates if isinstance(g, dict)]
    total = len(primary) if primary else 4
    passed = sum(1 for g in primary if g.get("pass"))
    if rs.get("gates_locked_count") is not None and primary:
        passed = max(0, total - int(rs.get("gates_locked_count") or 0))
    detail = json.dumps(gates, default=str) if gates else None
    return passed, total, detail


def _confidence_band(row: dict) -> tuple[float | None, float | None]:
    conf = _safe_float(row.get("plan_confidence"))
    if conf is None:
        conf = _safe_float(row.get("model_confidence_pct"))
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
    }

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
        "stop_swing": _band_low(st),
        "stop_build": _band_low(mt),
        "stop_thesis": _band_low(lt),
        "st_target": _band_high(st),
        "mt_target": _band_high(mt),
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
            conn.execute(
                "INSERT OR IGNORE INTO audit_meta(key, value) VALUES (?, ?)",
                ("schema_version", str(_SCHEMA_VERSION)),
            )
            conn.commit()

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
    ) -> int:
        q = "SELECT COUNT(*) AS n FROM signal_events WHERE 1=1"
        params: list[Any] = []
        if cohort_tag:
            q += " AND cohort_tag = ?"
            params.append(cohort_tag)
        if signal_date:
            q += " AND signal_date = ?"
            params.append(signal_date)
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
    ) -> list[dict[str, Any]]:
        allowed = allowed_cols or frozenset(
            {"gates_passed", "go_no_go", "market_cap_bucket", "ml_signal", "retail_verdict", "regime_label"}
        )
        if group_col not in allowed:
            return []
        q = f"""
            SELECT {group_col} AS bucket,
                   COUNT(*) AS n,
                   AVG(composite_score) AS avg_score,
                   SUM(CASE WHEN go_no_go = 'go' THEN 1 ELSE 0 END) AS n_go
            FROM signal_events
            WHERE cohort_tag = ? AND source = 'live'
            GROUP BY {group_col}
            ORDER BY n DESC
        """
        with self._connect() as conn:
            rows = conn.execute(q, (cohort_tag,)).fetchall()
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


def build_model_audit_payload(config: dict, data_root: Path | None = None) -> dict[str, Any]:
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
    pilot = store.get_pilot_status(cohort_tag, expected_tickers=len(cohort_tickers))
    pilot_target_days = int(audit_cfg.get("pilot_target_days", 30))
    distinct_days = int(pilot.get("distinct_days") or 0)

    last_date = pilot.get("last_date")
    last_session_count = store.count_events(cohort_tag=cohort_tag, signal_date=last_date) if last_date else 0
    captured_on_last = store.tickers_on_date(cohort_tag, last_date) if last_date else []
    missing_on_last = sorted(set(cohort_tickers) - set(captured_on_last)) if last_date else list(cohort_tickers)

    has_outcomes = False
    try:
        with store._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM signal_outcomes o JOIN signal_events e ON e.id = o.signal_event_id WHERE e.cohort_tag = ?",
                (cohort_tag,),
            ).fetchone()
            has_outcomes = bool(row and int(row["n"]) > 0)
    except Exception:
        pass

    message = None
    if distinct_days == 0:
        message = "No audit rows yet — run EOD / run_daily after deploy to populate signal_audit.db."
    elif last_session_count < len(cohort_tickers):
        message = f"Last session captured {last_session_count}/{len(cohort_tickers)} cohort tickers."

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
        "breakdown_by_gates": store.breakdown_rows(cohort_tag, "gates_passed"),
        "breakdown_by_go_no_go": store.breakdown_rows(cohort_tag, "go_no_go"),
        "breakdown_by_category": store.breakdown_rows(cohort_tag, "market_cap_bucket"),
        "breakdown_by_signal": store.breakdown_rows(cohort_tag, "ml_signal"),
        "breakdown_by_regime": store.breakdown_rows(cohort_tag, "regime_label"),
        "recent_records": store.list_records(cohort_tag=cohort_tag, limit=80),
        "outcomes_available": has_outcomes,
        "outcomes_note": "Outcome columns (7d/30d, win/loss) fill in Phase 2 after enough EOD history."
            if not has_outcomes
            else None,
        "message": message,
        "methodology": (
            "Fixed 100-ticker cohort logged once per EOD run (not on dashboard refresh). "
            "Separate from paper trading (~your watchlist/portfolio)."
        ),
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

    appended = 0
    skipped = 0
    missing = 0
    for sym in cohort:
        row = by_ticker.get(sym)
        if not row:
            missing += 1
            continue
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
    elif run_source == "dashboard" and not audit_cfg.get("log_on_dashboard", True):
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
    except Exception as e:
        logger.debug("paper_trades log failed: %s", e)
        out["paper_trades"] = {"error": str(e)}

    return out
