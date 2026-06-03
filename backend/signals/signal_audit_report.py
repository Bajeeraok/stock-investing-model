"""
Phase 3: audit reports + CSV export for the 100-ticker cohort pilot.

Writes DATA_ROOT/reports/audit_summary.json (+ optional CSV export).
"""
from __future__ import annotations

import csv
import io
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from signals.signal_audit_verdict import VERDICT_RULE_V1

logger = logging.getLogger(__name__)

CSV_COLUMNS: list[tuple[str, str]] = [
    ("signal_date", "signal_date"),
    ("signal_ts", "signal_ts"),
    ("ticker", "ticker"),
    ("market_cap_bucket", "category"),
    ("retail_verdict", "retail_verdict"),
    ("ml_signal", "ml_signal"),
    ("confidence_low", "confidence_low"),
    ("confidence_high", "confidence_high"),
    ("price_at_signal", "price_at_signal"),
    ("stop_swing", "stop_swing"),
    ("st_target", "st_target"),
    ("mt_target", "mt_target"),
    ("regime_label", "regime"),
    ("temperature", "temperature"),
    ("go_no_go", "go_no_go"),
    ("gates_passed", "gates_passed"),
    ("gates_total", "gates_total"),
    ("gates_failed", "gates_failed"),
    ("rsi", "rsi"),
    ("composite_score", "composite_score"),
    ("return_7d_pct", "return_7d_pct"),
    ("return_30d_pct", "return_30d_pct"),
    ("verdict", "verdict"),
    ("verdict_rule", "verdict_rule"),
    ("hit_st_target", "hit_st_target"),
    ("hit_stop_swing", "hit_stop_swing"),
    ("max_gain_pct", "max_gain_pct"),
    ("max_drawdown_pct", "max_drawdown_pct"),
    ("benchmark_return_30d_pct", "benchmark_spy_30d_pct"),
    ("run_source", "run_source"),
    ("track", "track"),
    ("velocity_triggered", "velocity_triggered"),
    ("velocity_score", "velocity_score"),
    ("rvol", "rvol"),
    ("bb_pct_b", "bb_pct_b"),
    ("readiness_tier", "readiness_tier"),
    ("readiness_score", "readiness_score"),
]


def _report_cfg(config: dict | None) -> dict[str, Any]:
    audit = (config or {}).get("signal_audit") or {}
    rc = audit.get("report") or {}
    return {
        "enabled": rc.get("enabled", True),
        "output_dir": str(rc.get("output_dir") or "reports"),
        "summary_filename": str(rc.get("summary_filename") or "audit_summary.json"),
        "export_filename": str(rc.get("export_filename") or "signal_audit_export.csv"),
        "resolve_before_build": rc.get("resolve_before_build", True),
    }


def _reports_dir(data_root: Path, config: dict | None) -> Path:
    rc = _report_cfg(config)
    d = data_root / rc["output_dir"]
    d.mkdir(parents=True, exist_ok=True)
    return d


def _since_date(days: int | None) -> str | None:
    if not days or days <= 0:
        return None
    try:
        from zoneinfo import ZoneInfo

        tz = ZoneInfo("America/New_York")
    except Exception:
        tz = None
    now = datetime.now(tz) if tz else datetime.now()
    return (now - timedelta(days=int(days))).strftime("%Y-%m-%d")


def build_audit_report(
    config: dict | None = None,
    data_root: Path | None = None,
    *,
    cohort_tag: str | None = None,
    days: int | None = None,
    write_files: bool = True,
) -> dict[str, Any]:
    """
    Build headline audit report JSON (and optional CSV on disk).
    """
    from config_loader import get_audit_cohort_tag, get_data_root, load_config
    from signals.signal_audit_store import SignalAuditStore, build_model_audit_payload

    if config is None:
        config = load_config()
    if data_root is None:
        data_root = get_data_root()

    rc = _report_cfg(config)
    tag = cohort_tag or get_audit_cohort_tag(config)
    since = _since_date(days)

    resolve_result = None
    if rc["resolve_before_build"]:
        try:
            from signals.signal_audit_outcomes import resolve_signal_audit_outcomes

            resolve_result = resolve_signal_audit_outcomes(config, data_root=data_root, cohort_tag=tag)
        except Exception as e:
            logger.debug("audit report resolve: %s", e)
            resolve_result = {"error": str(e)}

    store = SignalAuditStore(data_root=data_root)
    panel = build_model_audit_payload(config, data_root=data_root)
    outcome = store.outcome_summary(cohort_tag=tag, since_date=since)

    report: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "cohort_tag": tag,
        "days_filter": days,
        "since_date": since,
        "verdict_rule_version": VERDICT_RULE_V1,
        "methodology": {
            "horizons": "7 and 20 EOD snapshot steps after signal_date",
            "costs": "None on audit outcomes (research metric; paper trading uses round-trip cost separately)",
            "source": "live EOD captures only (source=live)",
            "cohort_file": (config.get("signal_audit") or {}).get("cohort_file"),
        },
        "pilot": panel.get("pilot"),
        "pilot_target_days": panel.get("pilot_target_days"),
        "pilot_progress_days": panel.get("pilot_progress_days"),
        "last_session": panel.get("last_session"),
        "outcome_summary": outcome,
        "breakdown_by_gates": panel.get("breakdown_by_gates"),
        "breakdown_by_go_no_go": panel.get("breakdown_by_go_no_go"),
        "breakdown_by_category": panel.get("breakdown_by_category"),
        "breakdown_by_signal": panel.get("breakdown_by_signal"),
        "breakdown_by_regime": panel.get("breakdown_by_regime"),
        "outcome_resolve": resolve_result,
    }

    paths: dict[str, str] = {}
    if write_files and rc["enabled"]:
        reports = _reports_dir(data_root, config)
        summary_path = reports / rc["summary_filename"]
        summary_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        paths["summary_json"] = str(summary_path)

        csv_text = export_records_csv(config, data_root=data_root, cohort_tag=tag, since_date=since)
        csv_path = reports / rc["export_filename"]
        csv_path.write_text(csv_text, encoding="utf-8")
        paths["export_csv"] = str(csv_path)

        store.save_daily_summary(
            summary_date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            cohort_tag=tag,
            n_signals=int(outcome.get("events_total") or 0),
            n_with_outcomes=int(outcome.get("resolved_n") or 0),
            payload=report,
        )
        paths["db_path"] = str(store.db_path)

    report["paths"] = paths
    return report


def export_records_csv(
    config: dict | None = None,
    data_root: Path | None = None,
    *,
    cohort_tag: str | None = None,
    since_date: str | None = None,
    limit: int = 10000,
    offset: int = 0,
) -> str:
    from config_loader import get_audit_cohort_tag, get_data_root, load_config
    from signals.signal_audit_store import SignalAuditStore

    if config is None:
        config = load_config()
    if data_root is None:
        data_root = get_data_root()
    tag = cohort_tag or get_audit_cohort_tag(config)
    store = SignalAuditStore(data_root=data_root)
    rows = store.list_records_with_outcomes(
        cohort_tag=tag,
        since_date=since_date,
        limit=limit,
        offset=offset,
    )
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([header for header, _ in CSV_COLUMNS])
    for row in rows:
        writer.writerow([row.get(key) for key, _ in CSV_COLUMNS])
    return buf.getvalue()


def list_audit_records(
    config: dict | None = None,
    data_root: Path | None = None,
    *,
    cohort_tag: str | None = None,
    since_date: str | None = None,
    limit: int = 200,
    offset: int = 0,
    ticker: str | None = None,
) -> dict[str, Any]:
    from config_loader import get_audit_cohort_tag, get_data_root, load_config
    from signals.signal_audit_store import SignalAuditStore

    if config is None:
        config = load_config()
    if data_root is None:
        data_root = get_data_root()
    tag = cohort_tag or get_audit_cohort_tag(config)
    store = SignalAuditStore(data_root=data_root)
    rows = store.list_records_with_outcomes(
        cohort_tag=tag,
        since_date=since_date,
        limit=limit,
        offset=offset,
        ticker=ticker,
    )
    total = store.count_events(cohort_tag=tag, since_date=since_date)
    return {
        "cohort_tag": tag,
        "since_date": since_date,
        "limit": limit,
        "offset": offset,
        "total": total,
        "records": rows,
    }


def audit_cohort_payload(config: dict | None = None) -> dict[str, Any]:
    from config_loader import (
        get_audit_cohort_meta,
        get_audit_cohort_tag,
        get_audit_cohort_tickers,
        load_signal_audit_cohort,
    )
    from config_loader import load_config

    if config is None:
        config = load_config()
    audit_cfg = config.get("signal_audit") or {}
    yaml_data = load_signal_audit_cohort(config)
    tickers = get_audit_cohort_tickers(config)
    meta = get_audit_cohort_meta(config)
    categories: dict[str, list[str]] = {}
    for cat, syms in (yaml_data.get("categories") or {}).items():
        if isinstance(syms, list):
            categories[str(cat)] = [str(t).upper() for t in syms if t]
    return {
        "enabled": bool(audit_cfg.get("enabled")),
        "cohort_tag": get_audit_cohort_tag(config),
        "cohort_size": len(tickers),
        "cohort_file": audit_cfg.get("cohort_file"),
        "categories": categories,
        "category_sizes": {k: len(v) for k, v in categories.items()},
        "ticker_meta": meta,
    }
