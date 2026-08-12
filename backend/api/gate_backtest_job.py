"""
Single-flight background gate-cohort backtest (scripts/backtest_gates.py logic).

Same pattern as api/eod_job.py: runs in a daemon thread so an HTTP request never
blocks on a multi-minute, multi-ticker rebuild. This is the API trigger for the
same job the script provides for shell/CLI use — added so it can be kicked off
from the dashboard's ad-hoc runner (or curl) without needing a shell on the
backend service, and so the heavy work happens off the request thread rather
than tying one up for minutes.

Two sources, matching the script:
  walkforward — rebuilds a panel from live OHLCV (causal); the regime gate falls
                back to a SPY-vs-SMA proxy for bars where per-ticker HMM history
                isn't available, which the walk-forward UI panel itself flags as
                less faithful than the live gate.
  eod         — reads real daily EOD snapshots (data/eod/*.json), enriching each
                with the gates as actually frozen at signal-log time — "production-
                like fidelity" per that same UI panel's own guidance. Needs a real
                EOD history to be useful (sparse locally; production has it).

Still real CPU + network work (live OHLCV fetch per ticker for forward returns,
either source) running in the same process as the live API — keep ticker counts
modest and avoid running this during high-traffic periods, same caution as any
other admin-triggered heavy job.
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
    source: str = "eod",
    period: str = "5y",
    step: int = 0,
    eod_days: int = 90,
    horizons: tuple[int, ...] = (21, 63, 126),
    buy_min: float = 0.0,
    min_gates_passed: int = 4,
    predict_ml: bool = False,
) -> bool:
    """Start the gate backtest in a background thread.

    source="eod" (default) uses real frozen daily gate snapshots — prefer this
    for a trustworthy read; source="walkforward" rebuilds from live OHLCV with
    the SPY-vs-SMA regime proxy noted in the module docstring.

    predict_ml (walkforward source only): run real ML inference per bar instead
    of leaving the ML gate defaulted to fail (the fast default — see the "ML gate
    requires ml_short_prob..." footnote in the report). Meaningfully slower;
    needed for a trustworthy read on the ML gate specifically in walkforward mode.

    Returns False (does not start a second run) if one is already in progress —
    single-flight, same as the EOD job, so an impatient double-click can't stack
    two multi-minute rebuilds on top of each other.
    """
    source = (source or "eod").strip().lower()
    if source not in ("eod", "walkforward"):
        source = "eod"

    with _lock:
        if _state.get("running"):
            return False
        _state["running"] = True
        _state["started_at"] = time.time()
        _state["finished_at"] = None
        _state["params"] = {
            "tickers": tickers,
            "source": source,
            "period": period,
            "step": step,
            "eod_days": eod_days,
            "horizons": list(horizons),
            "buy_min": buy_min,
            "min_gates_passed": min_gates_passed,
            "predict_ml": predict_ml,
        }
        _state["last_error"] = None

    def _worker() -> None:
        result = None
        error = None
        try:
            from pathlib import Path

            from config_loader import load_config
            from signals.gate_backtest import format_gate_backtest_report, summarize_gate_backtest

            cfg = load_config()
            ev = cfg.get("evaluation") or {}
            sell_max = float((cfg.get("score") or {}).get("sell_max", 35))
            tickers_set = set(tickers)

            if source == "eod":
                from scripts.backtest_gates import _list_eod_dates, rows_from_eod

                dates = _list_eod_dates(eod_days)
                if len(dates) < 3:
                    raise RuntimeError(
                        f"Only {len(dates)} EOD snapshot day(s) found under data/eod/ — "
                        "need at least 3 for the eod source. Use source=walkforward instead, "
                        "or run the EOD scheduler for a few more days first."
                    )
                logger.info(
                    "[gate-backtest-job] START source=eod tickers=%d eod_days=%d (found %d) horizons=%s",
                    len(tickers), eod_days, len(dates), horizons,
                )
                rows = rows_from_eod(dates=dates, horizons=horizons, tickers_filter=tickers_set)
            else:
                from signals.evaluation_harness import build_evaluation_panel

                if predict_ml:
                    gb_cfg = {**(ev.get("gate_backtest") or {}), "predict_ml": True}
                    ev = {**ev, "gate_backtest": gb_cfg}
                    cfg = {**cfg, "evaluation": ev}

                step_used = step or int(ev.get("default_step") or 5)
                logger.info(
                    "[gate-backtest-job] START source=walkforward tickers=%d period=%s step=%d horizons=%s predict_ml=%s",
                    len(tickers), period, step_used, horizons, predict_ml,
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
            summary["source"] = source

            out_json = Path(__file__).resolve().parent.parent / "data" / "evaluation" / "gate_backtest_summary.json"
            out_json.parent.mkdir(parents=True, exist_ok=True)
            import json as _json

            out_json.write_text(_json.dumps(summary, indent=2, default=str), encoding="utf-8")
            logger.info(
                "[gate-backtest-job] DONE source=%s panel_rows=%d saved=%s", source, len(rows), out_json,
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

    threading.Thread(target=_worker, name="gate-backtest", daemon=True).start()
    return True
