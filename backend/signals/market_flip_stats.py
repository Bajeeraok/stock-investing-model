"""
Market flip stats: gap-fade rates, event-day tables, pre-market vs close joins.

Heavy computation runs via scripts/build_market_flip_stats.py → market_flip_stats.json.
Runtime loads JSON for catalyst board / event scenarios.
"""
from __future__ import annotations

import calendar
import json
import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

EVENT_RELEASE_TIMES_ET: dict[str, str] = {
    "CPI": "08:30",
    "NFP": "08:30",
    "GDP": "08:30",
    "FOMC": "14:00",
}

# Re-export FOMC dates from event_scenarios to avoid duplication at import time
FOMC_DATES: list[str] = []


def _load_fomc_dates() -> list[str]:
    global FOMC_DATES
    if FOMC_DATES:
        return FOMC_DATES
    try:
        from signals.event_scenarios import FOMC_DATES as _FOMC

        FOMC_DATES = list(_FOMC)
    except Exception:
        FOMC_DATES = []
    return FOMC_DATES


def flip_stats_path(data_root: Path | None = None) -> Path:
    if data_root is None:
        from config_loader import get_data_root

        data_root = get_data_root()
    return Path(data_root) / "market_flip_stats.json"


def load_market_flip_stats(data_root: Path | None = None) -> dict[str, Any] | None:
    path = flip_stats_path(data_root)
    if not path.exists():
        bundled = Path(__file__).resolve().parent.parent / "data" / "market_flip_stats.json"
        path = bundled if bundled.exists() else path
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except Exception as e:
        logger.debug("load_market_flip_stats: %s", e)
        return None


def save_market_flip_stats(payload: dict[str, Any], data_root: Path | None = None) -> Path:
    path = flip_stats_path(data_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    return path


def _is_weekday(d: date) -> bool:
    return d.weekday() < 5


def _prior_business_day(d: date) -> date:
    cur = d - timedelta(days=1)
    while not _is_weekday(cur):
        cur -= timedelta(days=1)
    return cur


def generate_nfp_dates(start: date, end: date) -> list[str]:
    out: list[str] = []
    y, m = start.year, start.month
    end_y, end_m = end.year, end.month
    while (y, m) <= (end_y, end_m):
        first = date(y, m, 1)
        wd = first.weekday()
        days_to_fri = (4 - wd) % 7
        nfp = first + timedelta(days=days_to_fri)
        if start <= nfp <= end and _is_weekday(nfp):
            out.append(nfp.isoformat())
        if m == 12:
            y, m = y + 1, 1
        else:
            m += 1
    return out


def generate_cpi_dates(start: date, end: date) -> list[str]:
    """Approximate BLS CPI release (~12th of month, prior business day if weekend)."""
    out: list[str] = []
    y, m = start.year, start.month
    end_y, end_m = end.year, end.month
    while (y, m) <= (end_y, end_m):
        day = min(13, calendar.monthrange(y, m)[1])
        cpi = date(y, m, day)
        while not _is_weekday(cpi):
            cpi -= timedelta(days=1)
        if start <= cpi <= end:
            out.append(cpi.isoformat())
        if m == 12:
            y, m = y + 1, 1
        else:
            m += 1
    return out


def event_dates_for_type(event_type: str, start: date | None = None, end: date | None = None) -> list[str]:
    end = end or date.today()
    start = start or date(end.year - 13, end.month, min(end.day, 28))
    et = event_type.upper()
    if et == "FOMC":
        return [d for d in _load_fomc_dates() if start.isoformat() <= d <= end.isoformat()]
    if et == "NFP":
        return generate_nfp_dates(start, end)
    if et == "CPI":
        return generate_cpi_dates(start, end)
    return []


def _fetch_ohlc_frame(ticker: str, period: str = "13y"):
    try:
        import pandas as pd
        import yfinance as yf
    except ImportError:
        return None
    try:
        hist = yf.Ticker(ticker).history(period=period, auto_adjust=True)
        if hist is None or hist.empty:
            return None
        hist = hist.sort_index()
        out = pd.DataFrame(
            {
                "open": hist["Open"],
                "close": hist["Close"],
            }
        )
        return out.dropna()
    except Exception as e:
        logger.debug("fetch_ohlc %s: %s", ticker, e)
        return None


def _sign(x: float, eps: float = 1e-6) -> int:
    if x > eps:
        return 1
    if x < -eps:
        return -1
    return 0


def _match_trading_day(idx, target: date):
    import numpy as np

    try:
        mask = np.array([(x.date() if hasattr(x, "date") else x) >= target for x in idx])
        on_or_after = idx[mask]
        if len(on_or_after) == 0:
            return None
        return on_or_after[0]
    except Exception:
        return None


def compute_gap_fade_stats(
    event_dates: list[str],
    spy_df,
    es_df=None,
    *,
    label: str = "event",
) -> dict[str, Any] | None:
    """Gap sign (ES open or SPY open vs prior close) vs SPY same-day close sign."""
    import numpy as np

    if spy_df is None or len(spy_df) < 20:
        return None
    idx = spy_df.index
    fades = 0
    holds = 0
    flat = 0
    n = 0
    for d_str in event_dates:
        try:
            d_target = datetime.strptime(d_str, "%Y-%m-%d").date()
        except ValueError:
            continue
        event_day = _match_trading_day(idx, d_target)
        if event_day is None:
            continue
        pos = idx.get_loc(event_day)
        if isinstance(pos, slice) or (isinstance(pos, np.ndarray) and pos.ndim > 0):
            continue
        if pos == 0:
            continue
        prev_day = idx[pos - 1]
        try:
            prev_close = float(spy_df.loc[prev_day, "close"])
            day_close = float(spy_df.loc[event_day, "close"])
        except (KeyError, TypeError, ValueError):
            continue
        if not prev_close or prev_close <= 0:
            continue
        gap_open = None
        if es_df is not None and event_day in es_df.index:
            try:
                gap_open = float(es_df.loc[event_day, "open"])
            except (KeyError, TypeError, ValueError):
                gap_open = None
        if gap_open is None:
            try:
                gap_open = float(spy_df.loc[event_day, "open"])
            except (KeyError, TypeError, ValueError):
                continue
        gap_sign = _sign(gap_open - prev_close)
        close_sign = _sign(day_close - prev_close)
        if gap_sign == 0:
            flat += 1
            continue
        n += 1
        if gap_sign != close_sign:
            fades += 1
        else:
            holds += 1
    if n < 5:
        return None
    fade_pct = round(100 * fades / n, 1)
    return {
        "pct_gap_fade": fade_pct,
        "pct_gap_hold": round(100 * holds / n, 1),
        "n_events": n,
        "n_flat_gap": flat,
        "label": label,
        "rationale": f"Gap faded {fade_pct}% of {label} days (n={n}) — open gap sign ≠ SPY close vs prior close.",
    }


def compute_event_day_stats(event_type: str, event_dates: list[str], spy_df) -> dict[str, Any] | None:
    """Same-day and next-day SPY returns on event dates."""
    import numpy as np

    if spy_df is None or len(spy_df) < 100:
        return None
    idx = spy_df.index
    same_day: list[float] = []
    next_day: list[float] = []
    for d_str in event_dates:
        try:
            d_target = datetime.strptime(d_str, "%Y-%m-%d").date()
        except ValueError:
            continue
        event_day = _match_trading_day(idx, d_target)
        if event_day is None:
            continue
        pos = idx.get_loc(event_day)
        if isinstance(pos, slice) or (isinstance(pos, np.ndarray) and pos.ndim > 0):
            continue
        if pos == 0:
            continue
        prev_day = idx[pos - 1]
        try:
            prev_close = float(spy_df.loc[prev_day, "close"])
            event_close = float(spy_df.loc[event_day, "close"])
        except (KeyError, TypeError, ValueError):
            continue
        if prev_close and prev_close > 0:
            same_day.append(100 * (event_close - prev_close) / prev_close)
        later = idx[idx > event_day]
        if len(later) == 0:
            continue
        try:
            next_close = float(spy_df.loc[later[0], "close"])
        except (KeyError, TypeError, ValueError):
            continue
        if event_close and event_close > 0:
            next_day.append(100 * (next_close - event_close) / event_close)
    if len(next_day) < 5:
        return None
    arr_n = np.array(next_day)
    arr_s = np.array(same_day) if same_day else arr_n
    avg_n = float(np.mean(arr_n))
    std_n = float(np.std(arr_n, ddof=1)) if len(arr_n) > 1 else 0.0
    pct_pos = 100 * float(np.mean(arr_n > 0))
    avg_s = float(np.mean(arr_s)) if len(arr_s) >= 5 else None
    gap = compute_gap_fade_stats(event_dates, spy_df, label=event_type.lower())
    out: dict[str, Any] = {
        "event_type": event_type,
        "avg_return_pct": round(avg_n, 2),
        "avg_same_day_pct": round(avg_s, 2) if avg_s is not None else None,
        "std_pct": round(std_n, 2),
        "pct_positive": round(pct_pos, 1),
        "n_events": len(next_day),
        "rationale": f"Based on {len(next_day)} {event_type} events; SPY next-day avg {avg_n:+.2f}%, σ={std_n:.2f}%.",
    }
    if gap:
        out["gap_fade"] = gap
        out["pct_gap_fade"] = gap["pct_gap_fade"]
    return out


def compute_premarket_contradiction_stats(
    history_dir: Path,
    eod_dir: Path,
    *,
    min_samples: int = 5,
) -> dict[str, Any] | None:
    """Join archived pre-market bias vs SPY same-day direction."""
    if not history_dir.exists() or not eod_dir.exists():
        return None
    contradict = 0
    aligned = 0
    n = 0
    for pm_file in sorted(history_dir.glob("*.json")):
        date_str = pm_file.stem
        eod_file = eod_dir / f"{date_str}.json"
        if not eod_file.exists():
            continue
        try:
            with open(pm_file, encoding="utf-8") as f:
                pm = json.load(f)
            with open(eod_file, encoding="utf-8") as f:
                eod = json.load(f)
        except Exception:
            continue
        composite = pm.get("composite_score")
        try:
            composite = float(composite) if composite is not None else 0.0
        except (TypeError, ValueError):
            composite = 0.0
        pm_side = 1 if composite >= 0.08 else (-1 if composite <= -0.08 else 0)
        if pm_side == 0:
            continue
        spy_row = None
        for row in eod.get("signals") or eod.get("run_results") or []:
            if isinstance(row, dict) and str(row.get("ticker", "")).upper() == "SPY":
                spy_row = row
                break
        if not spy_row:
            continue
        chg = spy_row.get("change_pct") or spy_row.get("daily_change_pct")
        if chg is None:
            close = spy_row.get("close")
            prev = spy_row.get("prev_close")
            try:
                if close and prev and float(prev) > 0:
                    chg = 100 * (float(close) - float(prev)) / float(prev)
            except (TypeError, ValueError):
                chg = None
        if chg is None:
            continue
        try:
            chg_f = float(chg)
        except (TypeError, ValueError):
            continue
        day_side = 1 if chg_f > 0.05 else (-1 if chg_f < -0.05 else 0)
        if day_side == 0:
            continue
        n += 1
        if pm_side != day_side:
            contradict += 1
        else:
            aligned += 1
    if n < min_samples:
        return None
    pct = round(100 * contradict / n, 1)
    return {
        "pct_contradict": pct,
        "pct_aligned": round(100 * aligned / n, 1),
        "n_days": n,
        "rationale": f"Pre-market bias contradicted SPY close direction on {pct}% of days (n={n}).",
    }


def build_market_flip_stats(*, period: str = "13y") -> dict[str, Any]:
    """Compute full stats payload for JSON persistence."""
    end = date.today()
    start = date(end.year - 13, end.month, min(end.day, 28))
    spy = _fetch_ohlc_frame("SPY", period)
    es = _fetch_ohlc_frame("ES=F", period)

    from config_loader import get_data_root

    root = get_data_root()
    history_dir = root / "pre_market_history"
    eod_dir = root / "eod"

    events: dict[str, Any] = {}
    for et in ("FOMC", "CPI", "NFP"):
        dates = event_dates_for_type(et, start, end)
        stats = compute_event_day_stats(et, dates, spy)
        if stats:
            events[et] = stats

    gap_all = compute_gap_fade_stats(
        [d for dates in (event_dates_for_type(t, start, end) for t in ("CPI", "NFP", "FOMC")) for d in dates],
        spy,
        es_df=es,
        label="macro event",
    )

    pm_contra = compute_premarket_contradiction_stats(history_dir, eod_dir)

    return {
        "version": 1,
        "built_at": __import__("signals.time_et", fromlist=["now_iso_et"]).now_iso_et(),
        "period": period,
        "symbol": "SPY",
        "events": events,
        "gap_fade_all_macro": gap_all,
        "premarket_vs_close": pm_contra,
        "release_times_et": EVENT_RELEASE_TIMES_ET,
    }


def stats_for_event_type(event_type: str, flip_stats: dict[str, Any] | None) -> dict[str, Any] | None:
    """Lookup precomputed stats for catalyst / scenario UI."""
    if not flip_stats:
        return None
    ev = (flip_stats.get("events") or {}).get(event_type.upper())
    return ev if isinstance(ev, dict) else None
