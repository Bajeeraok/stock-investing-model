"""
Pre-market market catalyst board: scheduled macro today, live tape drivers,
tension flags (pre-market vs regime / next-day stats), and FOMC scenario stats.

P0 scope — decision support only; not a forecast of release outcomes.
"""
from __future__ import annotations

import datetime as _dt
import logging
from typing import Any

from signals.band_context import _HIGH_IMPACT, _parse_event_date
from signals.event_scenarios import EVENT_TYPE_KEYWORDS, get_event_reaction_stats
from signals.market_flip_stats import EVENT_RELEASE_TIMES_ET, load_market_flip_stats, stats_for_event_type

logger = logging.getLogger(__name__)

_FLIP_NARRATIVES: dict[str, list[str]] = {
    "FOMC": [
        "Hawkish dots / higher-for-longer → rates up, growth sells (bearish flip).",
        "Dovish hold or cut hint → yields drop, gap may hold (bullish continuation).",
    ],
    "CPI": [
        "Hot CPI → real yields up, multiple compression (bearish flip).",
        "Cool CPI → rate-cut hopes, risk-on continuation (bullish flip).",
    ],
    "NFP": [
        "Strong jobs + hot wages → Fed stays tight (headwind for multiples).",
        "Weak NFP → growth scare or cut hopes — watch yields for the real tell.",
    ],
    "GDP": [
        "Hot GDP → inflation stickiness fear; cold GDP → recession scare — both can flip tape.",
    ],
    "Other": [
        "Surprise vs consensus matters more than the headline — watch ES reaction into the number.",
    ],
}


def _classify_event(name: str) -> str:
    if not name:
        return "Other"
    n = name.lower()
    for event_type, keywords in EVENT_TYPE_KEYWORDS.items():
        if any(k in n for k in keywords):
            return event_type
    return "Other"


def _is_us_event(ev: dict) -> bool:
    country = (ev.get("country") or "").upper()
    return not country or country in ("US", "USA", "UNITED STATES")


def _is_high_impact(name: str) -> bool:
    nl = (name or "").lower()
    return any(k in nl for k in _HIGH_IMPACT)


def _premarket_bias_side(composite: float | None) -> str:
    if composite is None:
        return "neutral"
    if composite >= 0.08:
        return "bullish"
    if composite <= -0.08:
        return "bearish"
    return "neutral"


def _regime_side(regime: str | None) -> str:
    r = (regime or "").upper()
    if r == "UP" or "BULL" in r or "RISK-ON" in r:
        return "bullish"
    if r == "DOWN" or "BEAR" in r or "RISK-OFF" in r:
        return "bearish"
    return "neutral"


def _now_et() -> _dt.datetime:
    try:
        from zoneinfo import ZoneInfo
    except ImportError:
        from backports.zoneinfo import ZoneInfo  # type: ignore
    return _dt.datetime.now(ZoneInfo("America/New_York"))


def _parse_time_et(time_str: str | None) -> tuple[int, int] | None:
    if not time_str:
        return None
    try:
        parts = str(time_str).strip()[:5].split(":")
        return int(parts[0]), int(parts[1])
    except (ValueError, IndexError):
        return None


def _release_status(time_et: str | None, event_type: str, now: _dt.datetime | None = None) -> dict[str, Any]:
    """P2: pending vs released marker for 8:30 / 14:00 ET releases."""
    now = now or _now_et()
    default_time = EVENT_RELEASE_TIMES_ET.get(event_type.upper(), "08:30")
    tm = _parse_time_et(time_et) or _parse_time_et(default_time) or (8, 30)
    release_dt = now.replace(hour=tm[0], minute=tm[1], second=0, microsecond=0)
    released = now >= release_dt
    mins = int((release_dt - now).total_seconds() / 60) if not released else 0
    return {
        "time_et": f"{tm[0]:02d}:{tm[1]:02d}",
        "status": "released" if released else "pending",
        "minutes_until": max(0, mins) if not released else None,
        "minutes_since": int((now - release_dt).total_seconds() / 60) if released else None,
    }


def _scenario_for_event(event_type: str, flip_stats: dict | None) -> dict | None:
    pre = stats_for_event_type(event_type, flip_stats)
    if pre:
        return {
            "avg_return_pct": pre.get("avg_return_pct"),
            "avg_same_day_pct": pre.get("avg_same_day_pct"),
            "std_pct": pre.get("std_pct"),
            "pct_positive": pre.get("pct_positive"),
            "n_events": pre.get("n_events"),
            "pct_gap_fade": pre.get("pct_gap_fade"),
            "gap_fade": pre.get("gap_fade"),
            "rationale": pre.get("rationale"),
        }
    return get_event_reaction_stats(event_type, symbol="SPY")


def _intraday_context(scheduled_today: list[dict], now: _dt.datetime | None = None) -> dict[str, Any] | None:
    """P2: SPY since open and since first released macro event today."""
    now = now or _now_et()
    if now.weekday() >= 5:
        return None
    try:
        import yfinance as yf
    except ImportError:
        return None
    try:
        spy = yf.Ticker("SPY")
        hist = spy.history(period="1d", interval="5m", prepost=False)
        if hist is None or hist.empty:
            return None
        hist = hist.sort_index()
        try:
            from zoneinfo import ZoneInfo
        except ImportError:
            from backports.zoneinfo import ZoneInfo  # type: ignore
        et = ZoneInfo("America/New_York")
        idx_et = hist.index.tz_convert(et) if hist.index.tz else hist.index.tz_localize("UTC").tz_convert(et)
        open_bar = None
        for i, ts in enumerate(idx_et):
            if ts.hour == 9 and ts.minute >= 30:
                open_bar = float(hist.iloc[i]["Open"])
                break
        if open_bar is None and len(hist) > 0:
            open_bar = float(hist.iloc[0]["Open"])
        last = float(hist.iloc[-1]["Close"])
        if not open_bar or open_bar <= 0:
            return None
        since_open_pct = round(100 * (last - open_bar) / open_bar, 2)
        since_release: dict[str, Any] | None = None
        for ev in scheduled_today:
            rel = ev.get("release") or {}
            if rel.get("status") != "released":
                continue
            tm = _parse_time_et(rel.get("time_et") or ev.get("time_et"))
            if not tm:
                continue
            release_ts = now.replace(hour=tm[0], minute=tm[1], second=0, microsecond=0)
            mask = idx_et >= release_ts
            after = hist[mask]
            if after.empty:
                continue
            ref = float(after.iloc[0]["Open"])
            if ref > 0:
                since_release = {
                    "event_type": ev.get("event_type"),
                    "name": ev.get("name"),
                    "pct_since_release": round(100 * (last - ref) / ref, 2),
                    "release_time_et": rel.get("time_et"),
                }
                break
        return {
            "spy_last": round(last, 2),
            "spy_open": round(open_bar, 2),
            "since_open_pct": since_open_pct,
            "since_release": since_release,
            "as_of_et": now.strftime("%H:%M"),
        }
    except Exception as e:
        logger.debug("intraday_context: %s", e)
        return None


def _events_for_today(
    calendar_events: list[dict] | None,
    today: _dt.date,
    flip_stats: dict | None = None,
    now: _dt.datetime | None = None,
) -> list[dict]:
    out: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for ev in calendar_events or []:
        if not isinstance(ev, dict):
            continue
        if not _is_us_event(ev):
            continue
        name = (ev.get("name") or ev.get("event") or ev.get("title") or "").strip()
        if not name or not _is_high_impact(name):
            continue
        d = _parse_event_date(ev)
        if d is None or d != today:
            continue
        key = (d.isoformat(), name[:60])
        if key in seen:
            continue
        seen.add(key)
        event_type = _classify_event(name)
        scenario = _scenario_for_event(event_type, flip_stats) if event_type != "Other" else None
        time_raw = ev.get("time") or ev.get("date") or ""
        time_et = None
        if isinstance(time_raw, str) and len(time_raw) > 10:
            time_et = time_raw[11:16] if "T" in time_raw else time_raw[11:19][:5]
        if not time_et and event_type in EVENT_RELEASE_TIMES_ET:
            time_et = EVENT_RELEASE_TIMES_ET[event_type]
        release = _release_status(time_et, event_type, now=now)
        gap_line = None
        if scenario and scenario.get("pct_gap_fade") is not None:
            n = scenario.get("n_events") or scenario.get("gap_fade", {}).get("n_events")
            gap_line = f"Gap faded {scenario['pct_gap_fade']}% on past {event_type} days (n={n})"
        out.append({
            "date": d.isoformat(),
            "time_et": time_et or release.get("time_et"),
            "name": name[:120],
            "event_type": event_type,
            "impact": "High",
            "scenario": scenario,
            "release": release,
            "gap_fade_line": gap_line,
        })
    out.sort(key=lambda x: (x.get("time_et") or "99:99", x["name"]))
    return out


def _live_tape_drivers(premarket: dict | None, min_abs_score: float = 0.2) -> list[dict]:
    if not premarket:
        return []
    drivers: list[dict] = []
    for sig in premarket.get("signals") or []:
        if not isinstance(sig, dict):
            continue
        score = sig.get("score")
        if score is None:
            continue
        try:
            score = float(score)
        except (TypeError, ValueError):
            continue
        if abs(score) < min_abs_score:
            continue
        drivers.append({
            "name": sig.get("name") or "Signal",
            "raw_value": sig.get("raw_value") or "",
            "direction": sig.get("direction") or "Neutral",
            "score": round(score, 3),
            "category": sig.get("category") or "",
        })
    drivers.sort(key=lambda x: -abs(x["score"]))
    return drivers[:6]


def _tension_flags(
    premarket: dict | None,
    spy_regime: str | None,
    macro_regime: str | None,
    next_day_outlook: list[dict] | None,
    scheduled_today: list[dict],
) -> list[dict]:
    tensions: list[dict] = []
    composite = premarket.get("composite_score") if premarket else None
    try:
        composite = float(composite) if composite is not None else None
    except (TypeError, ValueError):
        composite = None
    pm_side = _premarket_bias_side(composite)
    regime_side = _regime_side(spy_regime or macro_regime)

    if pm_side == "bullish" and regime_side == "bearish":
        tensions.append({
            "level": "High",
            "code": "pm_bull_regime_bear",
            "message": "Pre-market bullish but SPY/macro regime bearish — gap-up into weak trend; elevated fade risk.",
        })
    elif pm_side == "bearish" and regime_side == "bullish":
        tensions.append({
            "level": "Medium",
            "code": "pm_bear_regime_bull",
            "message": "Pre-market bearish but regime still bullish — watch for dip-buying into the open.",
        })

    spy_outlook = next(
        (o for o in (next_day_outlook or []) if isinstance(o, dict) and str(o.get("ticker", "")).upper() == "SPY"),
        None,
    )
    if spy_outlook and pm_side != "neutral":
        bias = str(spy_outlook.get("bias") or "").lower()
        pct_green = spy_outlook.get("pct_green")
        if pm_side == "bullish" and "bear" in bias:
            tensions.append({
                "level": "Medium",
                "code": "pm_vs_state_bear",
                "message": f"Pre-market bull but SPY state history skews {spy_outlook.get('bias')} "
                f"({pct_green}% green in similar setups).",
            })
        elif pm_side == "bearish" and "bull" in bias:
            tensions.append({
                "level": "Medium",
                "code": "pm_vs_state_bull",
                "message": f"Pre-market bear but SPY state history skews {spy_outlook.get('bias')} "
                f"({pct_green}% green in similar setups).",
            })

    if scheduled_today and pm_side != "neutral":
        es_sig = _find_signal(premarket, ("S&P", "ES"))
        nq_sig = _find_signal(premarket, ("Nasdaq", "NQ"))
        gap_note = ""
        for sig in (es_sig, nq_sig):
            if sig and sig.get("raw_value"):
                gap_note = str(sig["raw_value"])
                break
        tensions.append({
            "level": "High" if len(scheduled_today) > 0 and pm_side == "bullish" else "Medium",
            "code": "macro_event_gap",
            "message": f"Macro release(s) today ({scheduled_today[0]['event_type']}) with pre-market "
            f"{pm_side}{f' ({gap_note})' if gap_note else ''} — classic gap-and-volatility setup.",
        })

    rot = (premarket or {}).get("rotation_risk_premarket")
    if rot in ("High", "Medium"):
        tensions.append({
            "level": "Medium" if rot == "Medium" else "High",
            "code": "rotation_risk",
            "message": f"Rotation risk {rot}: NQ/tech vs value/cyclicals divergence in pre-market.",
        })

    return tensions


def _find_signal(premarket: dict | None, needles: tuple[str, ...]) -> dict | None:
    for sig in (premarket or {}).get("signals") or []:
        if not isinstance(sig, dict):
            continue
        name = str(sig.get("name") or "")
        if any(n in name for n in needles):
            return sig
    return None


def _flip_narratives(scheduled_today: list[dict]) -> list[dict]:
    out: list[dict] = []
    seen_types: set[str] = set()
    for ev in scheduled_today:
        et = ev.get("event_type") or "Other"
        if et in seen_types:
            continue
        seen_types.add(et)
        bullets = _FLIP_NARRATIVES.get(et) or _FLIP_NARRATIVES["Other"]
        out.append({
            "event_type": et,
            "title": f"What could flip direction ({et})?",
            "bullets": bullets,
            "scenario": ev.get("scenario"),
        })
    if not out and not scheduled_today:
        out.append({
            "event_type": "Tape",
            "title": "What could flip direction today?",
            "bullets": [
                "Rates spike (10Y up) → pressure on growth/multiples.",
                "VIX breakout → risk-off rotation regardless of futures gap.",
                "Mega-cap earnings surprise → index-heavy move even without macro.",
            ],
            "scenario": None,
        })
    return out


def build_market_catalysts(
    premarket: dict | None = None,
    economic_calendar: list[dict] | None = None,
    next_day_outlook: list[dict] | None = None,
    spy_regime: str | None = None,
    macro_regime: str | None = None,
    *,
    today: _dt.date | None = None,
    config: dict | None = None,
) -> dict[str, Any]:
    """
    Build P0 catalyst board payload for pre-market UI.

    Returns scheduled_today, live_tape, tensions, flip_narratives, summary_line.
    """
    today = today or _now_et().date()
    now = _now_et()
    flip_stats = load_market_flip_stats()
    scheduled = _events_for_today(economic_calendar, today, flip_stats, now=now)
    live = _live_tape_drivers(premarket)
    tensions = _tension_flags(premarket, spy_regime, macro_regime, next_day_outlook, scheduled)
    flips = _flip_narratives(scheduled)
    intraday = _intraday_context(scheduled, now=now)

    ms_cfg = (config or {}).get("market_state") or {}
    is_premarket = now.weekday() < 5 and ((now.hour >= 4 and now.hour < 9) or (now.hour == 9 and now.minute < 30))
    is_rth = now.weekday() < 5 and ((now.hour == 9 and now.minute >= 30) or (10 <= now.hour < 16))
    polling = {
        "premarket_poll_ms": int(ms_cfg.get("premarket_poll_ms") or 300000),
        "intraday_poll_ms": int(ms_cfg.get("intraday_poll_ms") or 300000) if is_rth else 0,
        "is_premarket_et": is_premarket,
        "is_rth_et": is_rth,
    }

    composite = None
    bias = None
    if premarket:
        bias = premarket.get("bias")
        try:
            composite = float(premarket.get("composite_score"))
        except (TypeError, ValueError):
            composite = None

    parts: list[str] = []
    if bias:
        parts.append(f"Pre-market {bias}")
    if scheduled:
        parts.append(f"{len(scheduled)} macro catalyst(s) today")
    if tensions:
        parts.append(f"{len(tensions)} tension flag(s)")
    summary = " · ".join(parts) if parts else "No major scheduled catalysts today; tape-driven session."

    return {
        "as_of_date": today.isoformat(),
        "as_of_et": now.isoformat(),
        "summary_line": summary,
        "premarket_bias": bias,
        "premarket_composite": composite,
        "spy_regime": spy_regime,
        "macro_regime": macro_regime,
        "scheduled_today": scheduled,
        "live_tape": live,
        "tensions": tensions,
        "flip_narratives": flips,
        "intraday": intraday,
        "polling": polling,
        "premarket_vs_close": flip_stats.get("premarket_vs_close") if flip_stats else None,
        "digest_line": build_catalyst_digest_line(scheduled, premarket, flip_stats),
        "disclaimer": "Historical stats and setup flags only — not a forecast of release outcomes.",
    }


def attach_catalysts_to_premarket(premarket: dict, config: dict | None = None) -> dict:
    """Load calendar + SPY context and merge market_catalysts into pre-market payload."""
    config = config or {}
    calendar: list[dict] = []
    next_day: list[dict] = []
    spy_regime: str | None = None
    macro_regime: str | None = None

    try:
        from signals.cache import cached_economic_calendar
        from signals.fmp_client import fetch_economic_calendar

        def _fetch():
            ev, _ = fetch_economic_calendar(config, 14)
            return ev or []

        calendar = cached_economic_calendar(14, _fetch) or []
    except Exception as e:
        logger.debug("market_catalysts calendar: %s", e)

    try:
        from config_loader import get_data_root
        import json

        path = get_data_root() / "last_run.json"
        if path.exists():
            with open(path, encoding="utf-8") as f:
                payload = json.load(f)
            for row in payload.get("run_results") or []:
                if isinstance(row, dict) and str(row.get("ticker", "")).upper() == "SPY":
                    spy_regime = row.get("regime")
                    break
    except Exception as e:
        logger.debug("market_catalysts last_run: %s", e)

    try:
        from signals.cache import cached_next_day_backtest
        from signals.next_day_bias import next_day_outlook_for_symbols, run_next_day_backtest

        cache = {
            "SPY": cached_next_day_backtest("SPY", lambda: run_next_day_backtest("SPY", period="5y")),
        }
        next_day = next_day_outlook_for_symbols(["SPY"], cache)
    except Exception as e:
        logger.debug("market_catalysts next_day: %s", e)

    try:
        from signals.cache import get_cached_dashboard

        dash = get_cached_dashboard()
        if isinstance(dash, dict):
            macro_regime = dash.get("macro_regime") or macro_regime
            if not spy_regime:
                for row in dash.get("signals") or dash.get("signal_scores") or []:
                    if isinstance(row, dict) and str(row.get("ticker", "")).upper() == "SPY":
                        spy_regime = row.get("regime")
                        break
    except Exception as e:
        logger.debug("market_catalysts dashboard cache: %s", e)

    catalysts = build_market_catalysts(
        premarket=premarket,
        economic_calendar=calendar,
        next_day_outlook=next_day,
        spy_regime=spy_regime,
        macro_regime=macro_regime,
        config=config,
    )
    out = dict(premarket)
    out["market_catalysts"] = catalysts
    out["polling"] = catalysts.get("polling")
    _maybe_catalyst_push(config, catalysts)
    return out


def build_catalyst_digest_line(
    scheduled_today: list[dict],
    premarket: dict | None,
    flip_stats: dict | None,
) -> str | None:
    """P2 push hook: e.g. CPI in 30m; pre-market bull; gap-fade history 61%."""
    if not scheduled_today:
        return None
    ev = scheduled_today[0]
    rel = ev.get("release") or {}
    parts: list[str] = []
    if rel.get("status") == "pending" and rel.get("minutes_until") is not None:
        parts.append(f"{ev.get('event_type')} in {rel['minutes_until']}m")
    elif rel.get("status") == "released":
        parts.append(f"{ev.get('event_type')} released")
    bias = (premarket or {}).get("bias")
    if bias:
        parts.append(f"pre-market {str(bias).lower()}")
    gf = ev.get("scenario", {}).get("pct_gap_fade") if isinstance(ev.get("scenario"), dict) else None
    if gf is None and flip_stats:
        st = stats_for_event_type(str(ev.get("event_type")), flip_stats)
        gf = st.get("pct_gap_fade") if st else None
    if gf is not None:
        parts.append(f"gap-fade history {gf}%")
    return "; ".join(parts) if parts else None


def _maybe_catalyst_push(config: dict, catalysts: dict) -> None:
    alerts = (config.get("alerts") or {}) if config else {}
    if alerts.get("catalyst_push_enabled") is False:
        return
    line = catalysts.get("digest_line")
    if not line:
        return
    try:
        from behavior.push_digest import maybe_broadcast_catalyst_push

        maybe_broadcast_catalyst_push(config, line)
    except Exception as e:
        logger.debug("catalyst push: %s", e)
