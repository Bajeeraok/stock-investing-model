"""
Historical backtest for swing classifier setups (T1 / T2 / stop / time stop).

Replays swing_* fields from EOD rows (or recomputes via swing_engine) and walks
forward on daily OHLCV to score mechanical exit rules.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from signals.swing_engine import attach_swing_to_row, compute_swing_fields


def _sf(v) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
        return f if f == f else None
    except (TypeError, ValueError):
        return None


def enrich_eod_row_with_swing(
    row: dict[str, Any],
    *,
    config: dict | None = None,
    recompute: bool = False,
) -> dict[str, Any]:
    """Ensure row has swing_* fields (reuse EOD snapshot or recompute)."""
    out = dict(row)
    if not recompute and out.get("swing_setup_type"):
        return out
    fields = compute_swing_fields(out, config=config)
    out.update(fields)
    return out


def simulate_swing_trade(
    ohlcv: pd.DataFrame,
    signal_date: str,
    *,
    entry_price: float,
    stop: float,
    t1: float,
    t2: float,
    horizon_days: int,
) -> dict[str, Any]:
    """
    Bar-by-bar simulation from signal_date close entry.
    Priority each day: stop (low) → t1 (high) → t2 (high); time stop at horizon.
    """
    if ohlcv is None or ohlcv.empty or entry_price <= 0:
        return {"verdict": "SKIP", "reason": "no_ohlcv"}

    df = ohlcv.sort_index()
    try:
        sig_ts = pd.Timestamp(signal_date).normalize()
        loc = int(df.index.get_indexer([sig_ts], method="nearest")[0])
    except Exception:
        return {"verdict": "SKIP", "reason": "bad_signal_date"}

    if loc < 0 or loc >= len(df):
        return {"verdict": "SKIP", "reason": "signal_date_oob"}

    end = min(len(df) - 1, loc + max(1, int(horizon_days)))
    hit_stop = hit_t1 = hit_t2 = False
    exit_day = None
    exit_price = None
    exit_reason = None

    for i in range(loc + 1, end + 1):
        bar = df.iloc[i]
        hi = _sf(bar.get("High") if "High" in bar.index else bar.get("high"))
        lo = _sf(bar.get("Low") if "Low" in bar.index else bar.get("low"))
        cl = _sf(bar.get("Close") if "Close" in bar.index else bar.get("close"))
        if hi is None:
            hi = cl
        if lo is None:
            lo = cl
        if cl is None:
            continue
        day = df.index[i]
        day_str = day.strftime("%Y-%m-%d") if hasattr(day, "strftime") else str(day)[:10]

        if stop and lo is not None and lo <= stop:
            hit_stop = True
            exit_day = day_str
            exit_price = stop
            exit_reason = "stop"
            break
        if t1 and hi is not None and hi >= t1 and not hit_t1:
            hit_t1 = True
            if t2 and hi >= t2:
                hit_t2 = True
                exit_day = day_str
                exit_price = t2
                exit_reason = "t2"
                break
            exit_day = day_str
            exit_price = t1
            exit_reason = "t1"
            break

    if exit_reason is None:
        exit_day = df.index[end].strftime("%Y-%m-%d") if hasattr(df.index[end], "strftime") else str(df.index[end])[:10]
        last = df.iloc[end]
        exit_price = _sf(last.get("Close") if "Close" in last.index else last.get("close")) or entry_price
        exit_reason = "time_stop"

    ret_pct = round(100.0 * (float(exit_price) - entry_price) / entry_price, 4) if exit_price else None
    verdict = "WIN" if ret_pct is not None and ret_pct > 0 and not hit_stop else (
        "LOSS" if hit_stop or (ret_pct is not None and ret_pct <= 0) else "FLAT"
    )

    return {
        "verdict": verdict,
        "exit_reason": exit_reason,
        "exit_day": exit_day,
        "exit_price": round(float(exit_price), 4) if exit_price is not None else None,
        "return_pct": ret_pct,
        "hit_stop": hit_stop,
        "hit_t1": hit_t1,
        "hit_t2": hit_t2,
        "horizon_days": horizon_days,
        "entry_price": round(entry_price, 4),
    }


def backtest_swing_row(
    row: dict[str, Any],
    *,
    signal_date: str,
    ohlcv: pd.DataFrame | None,
    config: dict | None = None,
    recompute_swing: bool = False,
) -> dict[str, Any] | None:
    """Single EOD row → simulated swing outcome."""
    enriched = enrich_eod_row_with_swing(row, config=config, recompute=recompute_swing)
    if not enriched.get("swing_triggered"):
        return None

    entry = _sf(enriched.get("close") or enriched.get("price"))
    stop = _sf(enriched.get("swing_stop"))
    t1 = _sf(enriched.get("swing_t1"))
    t2 = _sf(enriched.get("swing_t2"))
    horizon = int(_sf(enriched.get("swing_horizon_trading_days")) or 12)
    if entry is None or ohlcv is None:
        return None

    sim = simulate_swing_trade(
        ohlcv,
        signal_date,
        entry_price=entry,
        stop=stop or entry * 0.97,
        t1=t1 or entry * 1.03,
        t2=t2 or entry * 1.05,
        horizon_days=horizon,
    )
    return {
        "ticker": enriched.get("ticker"),
        "date": signal_date,
        "swing_setup_type": enriched.get("swing_setup_type"),
        "swing_score": enriched.get("swing_score"),
        "swing_verdict": enriched.get("swing_verdict"),
        "go_no_go": enriched.get("go_no_go"),
        **sim,
    }


def _pct(n: int, d: int) -> float | None:
    return round(100.0 * n / d, 2) if d else None


def summarize_swing_backtest(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate simulated swing trades."""
    n = len(results)
    if not n:
        return {"n": 0, "message": "No swing_triggered signals in sample."}

    wins = sum(1 for r in results if r.get("verdict") == "WIN")
    losses = sum(1 for r in results if r.get("verdict") == "LOSS")
    rets = [float(r["return_pct"]) for r in results if r.get("return_pct") is not None]
    avg_ret = round(sum(rets) / len(rets), 4) if rets else None

    by_setup: dict[str, list[dict]] = {}
    for r in results:
        st = str(r.get("swing_setup_type") or "unknown")
        by_setup.setdefault(st, []).append(r)

    by_setup_summary = {}
    for st, rows in sorted(by_setup.items()):
        wr = _pct(sum(1 for x in rows if x.get("verdict") == "WIN"), len(rows))
        by_setup_summary[st] = {
            "n": len(rows),
            "win_rate_pct": wr,
            "avg_return_pct": round(
                sum(float(x["return_pct"]) for x in rows if x.get("return_pct") is not None)
                / max(1, sum(1 for x in rows if x.get("return_pct") is not None)),
                4,
            )
            if any(x.get("return_pct") is not None for x in rows)
            else None,
        }

    exit_counts = {}
    for r in results:
        er = str(r.get("exit_reason") or "unknown")
        exit_counts[er] = exit_counts.get(er, 0) + 1

    go_rows = [r for r in results if str(r.get("go_no_go") or "").lower() == "go"]
    no_go_rows = [r for r in results if str(r.get("go_no_go") or "").lower() == "no_go"]

    return {
        "n": n,
        "win_rate_pct": _pct(wins, n),
        "loss_rate_pct": _pct(losses, n),
        "avg_return_pct": avg_ret,
        "exit_reason_counts": exit_counts,
        "by_setup_type": by_setup_summary,
        "go_cohort": {
            "n": len(go_rows),
            "win_rate_pct": _pct(sum(1 for x in go_rows if x.get("verdict") == "WIN"), len(go_rows)),
        },
        "no_go_cohort": {
            "n": len(no_go_rows),
            "win_rate_pct": _pct(sum(1 for x in no_go_rows if x.get("verdict") == "WIN"), len(no_go_rows)),
        },
        "hit_t1_pct": _pct(sum(1 for r in results if r.get("hit_t1")), n),
        "hit_t2_pct": _pct(sum(1 for r in results if r.get("hit_t2")), n),
        "hit_stop_pct": _pct(sum(1 for r in results if r.get("hit_stop")), n),
    }


def format_swing_backtest_report(summary: dict[str, Any]) -> str:
    if not summary.get("n"):
        return summary.get("message") or "No swing backtest results."

    lines = [
        "=== Swing setup backtest ===",
        f"Signals: {summary['n']}",
        f"Win rate: {summary.get('win_rate_pct')}%  |  Avg return: {summary.get('avg_return_pct')}%",
        f"T1 hit: {summary.get('hit_t1_pct')}%  |  T2 hit: {summary.get('hit_t2_pct')}%  |  Stop: {summary.get('hit_stop_pct')}%",
        f"Exit mix: {summary.get('exit_reason_counts')}",
        "",
        "By setup type:",
    ]
    for st, block in (summary.get("by_setup_type") or {}).items():
        lines.append(
            f"  {st}: n={block.get('n')} win={block.get('win_rate_pct')}% avg={block.get('avg_return_pct')}%"
        )
    go = summary.get("go_cohort") or {}
    ng = summary.get("no_go_cohort") or {}
    lines.extend(
        [
            "",
            f"4-gate GO cohort: n={go.get('n')} win={go.get('win_rate_pct')}%",
            f"4-gate NO-GO cohort: n={ng.get('n')} win={ng.get('win_rate_pct')}%",
            "",
            "Note: swing track is technical-first; NO-GO cohort is expected to diverge from accumulate gates.",
        ]
    )
    return "\n".join(lines)
