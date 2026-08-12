"""
Single-flight background gate-cohort backtest (scripts/backtest_gates.py, walk-forward source).

Same pattern as api/eod_job.py: runs in a daemon thread so an HTTP request never
blocks on a multi-minute, multi-ticker walk-forward rebuild. This is the API
trigger for the same job the script provides for shell/CLI use — added so it
can be kicked off from the dashboard's ad-hoc runner (or curl) without needing
a shell on the backend service, and so the heavy work happens off the request
thread rather than tying one up for minutes.

Still real CPU + network work (live OHLCV fetch per ticker) running in the same
process as the live API — keep ticker counts modest and avoid running this
during high-traffic periods, same caution as any other admin-triggered heavy job.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any

logger = logging.getLogger("api.gate_backtest_job")

_lock = threading.Lock()
_state: dict[str, Any] = {
    "running": False,
    "started_at": None,
    "finished_at": None,
    "params": None,
    "last_result": None,
    "last_error": None,
}


def gate_backtest_job_state() -> dict[str, Any]:
    with _lock:
        return dict(_state)


def start_gate_backtest_job(
    *,
    tickers: list[str],
    period: str = "5y",
    step: int = 0,
    horizons: tuple[int, ...] = (21, 63, 126),
    buy_min: float = 0.0,
    min_gates_passed: int = 4,
) -> bool:
    """Start the walk-forward gate backtest in a background thread.

    Returns False (does not start a second run) if one is already in progress —
    single-flight, same as the EOD job, so an impatient double-click can't stack
    two multi-minute walk-forward rebuilds on top of each other.
    """
    with _lock:
        if _state.get("running"):
            return False
        _state["running"] = True
        _state["started_at"] = time.time()
        _state["finished_at"] = None
        _state["params"] = {
            "tickers": tickers,
            "period": period,
            "step": step,
            "horizons": list(horizons),
            "buy_min": buy_min,
            "min_gates_passed": min_gates_passed,
        }
        _state["last_error"] = None

    def _worker() -> None:
        result = None
        error = None
        try:
            from pathlib import Path

            from config_loader import load_config
            from signals.evaluation_harness import build_evaluation_panel
            from signals.gate_backtest import format_gate_backtest_report, summarize_gate_backtest

            cfg = load_config()
            ev = cfg.get("evaluation") or {}
            step_used = step or int(ev.get("default_step") or 5)
            sell_max = float((cfg.get("score") or {}).get("sell_max", 35))

            logger.info(
                "[gate-backtest-job] START tickers=%d period=%s step=%d horizons=%s",
                len(tickers), period, step_used, horizons,
            )
            rows = build_evaluation_panel(
                tickers,
                config=cfg,
                period=period,
                step=step_used,
                horizons=horizons,
                spy_ticker=str(ev.get("spy_ticker") or "SPY"),
            )
            summary = summarize_gate_backtest(
                rows,
                horizons=horizons,
                buy_min=buy_min or float((cfg.get("score") or {}).get("buy_min", 70)),
                min_gates_passed=max(1, min(4, min_gates_passed)),
                sell_max=sell_max,
            )
            summary["report_text"] = format_gate_backtest_report(summary)
            summary["panel_rows"] = len(rows)
            summary["tickers"] = tickers

            out_json = Path(__file__).resolve().parent.parent / "data" / "evaluation" / "gate_backtest_summary.json"
            out_json.parent.mkdir(parents=True, exist_ok=True)
            import json as _json

            out_json.write_text(_json.dumps(summary, indent=2, default=str), encoding="utf-8")
            logger.info(
                "[gate-backtest-job] DONE panel_rows=%d saved=%s", len(rows), out_json,
            )
            result = summary
        except Exception as e:
            error = str(e)
            logger.exception("[gate-backtest-job] failed")
        finally:
            with _lock:
                _state["running"] = False
                _state["finished_at"] = time.time()
                _state["last_result"] = result
                _state["last_error"] = error

    threading.Thread(target=_worker, name="gate-backtest-walkforward", daemon=True).start()
    return True
