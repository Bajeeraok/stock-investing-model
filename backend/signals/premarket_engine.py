"""
Pre-market signal engine: 6 categories, 15 sources, confidence-weighted composite.
Design: Equity Futures 35%, International 20%, Volatility 10%, Rates 12%,
        Currencies 8%, Commodities 10%, Crypto+Mega-cap 5%.
- Crude oil: moderate rise (+0.5% to +1.5%) = growth = bullish; spike/crash >2.5% = bearish.
- VIX: level AND direction (22 falling vs 22 rising scored separately then combined).
- Yen: USD/JPY rising = yen weakening = risk-on = bullish (inverted).
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import Enum
from typing import Optional
import time

try:
    import yfinance as yf
    import pandas as pd
except ImportError:
    yf = None
    pd = None

from signals.fetcher import fetch_ohlcv_safe


class Bias(str, Enum):
    STRONG_BULL = "STRONG BULL"
    BULL = "BULL"
    SLIGHT_BULL = "SLIGHT BULL"
    NEUTRAL = "NEUTRAL"
    SLIGHT_BEAR = "SLIGHT BEAR"
    BEAR = "BEAR"
    STRONG_BEAR = "STRONG BEAR"


@dataclass
class PreMarketSignal:
    name: str
    score: float  # -1.0 to +1.0
    weight: float
    raw_value: str
    direction: str  # "Bullish" | "Bearish" | "Neutral"
    confidence: float  # 0.0 to 1.0
    note: Optional[str] = None
    as_of: Optional[str] = None  # date of the latest bar behind raw_value
    stale: bool = False  # latest bar is from a prior session → excluded from the composite


@dataclass
class PreMarketReport:
    timestamp: "datetime"
    composite_score: float
    bias: Bias
    confidence: float
    minutes_to_open: int
    top_bullish: list[str]
    top_bearish: list[str]
    key_risks: list[str]
    suggested_tickers: dict[str, list[str]]  # sector_plays
    signals: list[PreMarketSignal]


def _pct(prior: float, last: float) -> Optional[float]:
    if prior is None or last is None or prior <= 0:
        return None
    return round(100 * (last - prior) / prior, 2)


def _prior_and_last(close) -> tuple[Optional[float], Optional[float]]:
    if close is None or len(close) < 2:
        return None, None
    prev = float(close.iloc[-2])
    last = float(close.iloc[-1])
    return prev, last


def _session_ref_date() -> date:
    """Most recent weekday (ET): bars older than this are a prior session's move."""
    from signals.time_et import now_et

    d = now_et().date()
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def _last_bar_date(close) -> Optional[date]:
    try:
        return close.index[-1].date()
    except Exception:
        return None


def _mark_stale(sig: "PreMarketSignal", bar_date: Optional[date]) -> "PreMarketSignal":
    """Tag with its bar date; a prior-session move is labelled and dropped from the composite."""
    if bar_date is None or sig.confidence <= 0:
        return sig
    sig.as_of = bar_date.isoformat()
    if bar_date < _session_ref_date():
        sig.stale = True
        sig.confidence = 0
        sig.score = 0.0
        sig.direction = "Neutral"
        sig.raw_value = f"{sig.raw_value} ({bar_date:%b} {bar_date.day})"
        sig.note = "Last session's move, not today's — left out of the score."
    return sig


def _us_listed_move(sym: str) -> tuple[Optional[float], Optional[date]]:
    """US stock/ETF % move: today's session if it has opened, else pre-market price vs prior close."""
    close = fetch_ohlcv_safe(sym, "5d")
    prev, last = _prior_and_last(close)
    d = _last_bar_date(close)
    if prev is None or last is None or d is None:
        return None, None
    today = _session_ref_date()
    if d >= today:
        return _pct(prev, last), d
    try:
        bars = yf.download(sym, period="1d", interval="5m", prepost=True, progress=False, threads=False)
        if bars is not None and not bars.empty:
            if hasattr(bars.columns, "levels"):
                bars.columns = [c[0] if isinstance(c, tuple) else c for c in bars.columns]
            px = bars["Close"].dropna()
            if px.index.tz is not None:
                px.index = px.index.tz_convert("America/New_York")
            px = px[px.index.date == today]
            if len(px):
                return _pct(last, float(px.iloc[-1])), today
    except Exception:
        pass
    return _pct(prev, last), d


def _score_to_direction(score: float) -> str:
    if score > 0.15:
        return "Bullish"
    if score < -0.15:
        return "Bearish"
    return "Neutral"


# ─── Equity Futures (35% total: ES 17.5%, NQ 17.5%) ─────────────────────────
def _fetch_futures() -> list[PreMarketSignal]:
    out = []
    weight = 0.175
    for name, sym in [("S&P 500 Futures (ES=F)", "ES=F"), ("Nasdaq Futures (NQ=F)", "NQ=F")]:
        close = fetch_ohlcv_safe(sym, "5d")
        prev, last = _prior_and_last(close)
        pct = _pct(prev, last) if (prev and last) else None
        if pct is None:
            out.append(PreMarketSignal(name=name, score=0, weight=weight, raw_value="N/A", direction="Neutral", confidence=0, note="No data"))
            continue
        score = max(-1, min(1, pct / 1.5))
        out.append(_mark_stale(PreMarketSignal(
            name=name, score=score, weight=weight, raw_value=f"{pct:+.2f}% ({sym})",
            direction=_score_to_direction(score), confidence=1.0
        ), _last_bar_date(close)))
        time.sleep(0.2)
    return out


# ─── International (20%: Europe live + Asia close) ──────────────────────────
def _fetch_international() -> list[PreMarketSignal]:
    out = []
    # Local indexes: DAX trades during US pre-market; Nikkei closes ~1:30 AM ET the same date.
    # (US-listed EWG/EWJ have no bar for today before 9:30, so they showed yesterday's move.)
    for name, sym, w in [("Europe (DAX)", "^GDAXI", 0.10), ("Asia close (Nikkei 225)", "^N225", 0.10)]:
        close = fetch_ohlcv_safe(sym, "5d")
        prev, last = _prior_and_last(close)
        pct = _pct(prev, last) if (prev and last) else None
        if pct is None:
            out.append(PreMarketSignal(name=name, score=0, weight=w, raw_value="N/A", direction="Neutral", confidence=0))
            continue
        score = max(-1, min(1, pct / 2.0))
        out.append(_mark_stale(PreMarketSignal(
            name=name, score=score, weight=w, raw_value=f"{pct:+.2f}%",
            direction=_score_to_direction(score), confidence=1.0
        ), _last_bar_date(close)))
        time.sleep(0.2)
    return out


# ─── Volatility (10%): VIX level AND direction ───────────────────────────────
def _fetch_volatility() -> list[PreMarketSignal]:
    out = []
    close = fetch_ohlcv_safe("^VIX", "5d")
    if close is None or len(close) < 3:
        return [PreMarketSignal(name="VIX level + direction", score=0, weight=0.10, raw_value="N/A", direction="Neutral", confidence=0)]
    level = float(close.iloc[-1])
    prev_level = float(close.iloc[-2])
    change = level - prev_level
    # Level: <18 bullish, 18-22 neutral, >22 bearish
    if level < 18:
        level_score = 0.4
    elif level < 22:
        level_score = 0
    else:
        level_score = -0.5 - (level - 22) * 0.02
    level_score = max(-1, min(1, level_score))
    # Direction: falling = bullish, rising = bearish
    if change < -0.5:
        dir_score = 0.3
    elif change > 0.5:
        dir_score = -0.3
    else:
        dir_score = 0
    combined = (level_score * 0.6 + dir_score * 0.4)
    combined = max(-1, min(1, combined))
    raw = f"VIX {level:.1f} ({change:+.1f})"
    out.append(_mark_stale(PreMarketSignal(
        name="VIX level + direction", score=combined, weight=0.10, raw_value=raw,
        direction=_score_to_direction(combined), confidence=1.0,
        note="Level and intraday direction scored separately then combined."
    ), _last_bar_date(close)))
    return out


# ─── Fixed Income (12%): 10Y yield + curve proxy ─────────────────────────────
def _fetch_rates() -> list[PreMarketSignal]:
    out = []
    # ^TNX = 10Y yield; ^IRX = 13-week (short end). Curve = TNX - IRX proxy (we use TNX move as proxy)
    tnx = fetch_ohlcv_safe("^TNX", "5d")
    prev, last = _prior_and_last(tnx)
    if prev is None or last is None:
        return [PreMarketSignal(name="10Y yield", score=0, weight=0.12, raw_value="N/A", direction="Neutral", confidence=0)]
    pct = _pct(prev, last)
    # Yield up = bearish for equities (rate up = discount rate up)
    score = -max(-1, min(1, (pct or 0) / 5.0))
    out.append(_mark_stale(PreMarketSignal(
        name="10Y Treasury yield", score=score, weight=0.12,
        raw_value=f"{last:.2f}% ({pct:+.2f}% chg)", direction=_score_to_direction(score), confidence=1.0
    ), _last_bar_date(tnx)))
    return out


# ─── Currencies (8%): DXY 4%, USD/JPY 4%) — Yen inverted ────────────────────
def _fetch_currencies() -> list[PreMarketSignal]:
    out = []
    # DXY: up = dollar strong = often risk-off = bearish equities
    dxy = fetch_ohlcv_safe("DX-Y.NYB", "5d")
    prev, last = _prior_and_last(dxy)
    pct = _pct(prev, last) if (prev and last) else None
    if pct is not None:
        score = -max(-1, min(1, pct / 1.0))
        out.append(_mark_stale(PreMarketSignal(
            name="DXY", score=score, weight=0.04, raw_value=f"{pct:+.2f}%",
            direction=_score_to_direction(score), confidence=1.0
        ), _last_bar_date(dxy)))
    else:
        out.append(PreMarketSignal(name="DXY", score=0, weight=0.04, raw_value="N/A", direction="Neutral", confidence=0))
    time.sleep(0.2)
    # USD/JPY: up = yen weakening = risk-on = BULLISH (inverted)
    jpy = fetch_ohlcv_safe("JPY=X", "5d")
    prev, last = _prior_and_last(jpy)
    pct = _pct(prev, last) if (prev and last) else None
    if pct is not None:
        score = max(-1, min(1, pct / 1.0))
        out.append(_mark_stale(PreMarketSignal(
            name="USD/JPY (Yen inverted)", score=score, weight=0.04, raw_value=f"{pct:+.2f}%",
            direction=_score_to_direction(score), confidence=1.0,
            note="USD/JPY up = yen weakening = risk-on = bullish."
        ), _last_bar_date(jpy)))
    else:
        out.append(PreMarketSignal(name="USD/JPY", score=0, weight=0.04, raw_value="N/A", direction="Neutral", confidence=0))
    return out


# ─── Commodities (10%): Copper, Gold, Crude — Crude non-linear ───────────────
def _fetch_commodities() -> list[PreMarketSignal]:
    out = []
    # Copper: growth proxy, up = bullish
    cp = fetch_ohlcv_safe("HG=F", "5d")
    prev, last = _prior_and_last(cp)
    pct = _pct(prev, last) if (prev and last) else None
    if pct is not None:
        score = max(-1, min(1, pct / 2.0))
        out.append(_mark_stale(PreMarketSignal(
            name="Copper", score=score, weight=0.033, raw_value=f"{pct:+.2f}%",
            direction=_score_to_direction(score), confidence=1.0
        ), _last_bar_date(cp)))
    else:
        out.append(PreMarketSignal(name="Copper", score=0, weight=0.033, raw_value="N/A", direction="Neutral", confidence=0))
    time.sleep(0.2)
    # Gold: risk-off up = bearish equities
    gld = fetch_ohlcv_safe("GC=F", "5d")
    prev, last = _prior_and_last(gld)
    pct = _pct(prev, last) if (prev and last) else None
    if pct is not None:
        score = -max(-1, min(1, pct / 1.5))
        out.append(_mark_stale(PreMarketSignal(
            name="Gold", score=score, weight=0.033, raw_value=f"{pct:+.2f}%",
            direction=_score_to_direction(score), confidence=1.0
        ), _last_bar_date(gld)))
    else:
        out.append(PreMarketSignal(name="Gold", score=0, weight=0.033, raw_value="N/A", direction="Neutral", confidence=0))
    time.sleep(0.2)
    # Crude: non-linear — +0.5 to +1.5% = growth = bullish; >2.5% or <-2.5% = bearish
    crude = fetch_ohlcv_safe("CL=F", "5d")
    prev, last = _prior_and_last(crude)
    pct = _pct(prev, last) if (prev and last) else None
    if pct is not None:
        if 0.5 <= pct <= 1.5:
            score = 0.4
            note = "Moderate rise = growth signal."
        elif -0.5 <= pct <= 0.5:
            score = 0
            note = "Flat."
        elif pct > 2.5 or pct < -2.5:
            score = -0.6
            note = "Sharp move = inflation fear or demand destruction."
        elif pct > 1.5:
            score = -0.2
            note = "Strong rise = inflation concern."
        else:
            score = -0.2
            note = "Sharp drop = demand concern."
        score = max(-1, min(1, score))
        out.append(_mark_stale(PreMarketSignal(
            name="Crude Oil (non-linear)", score=score, weight=0.034, raw_value=f"{pct:+.2f}%",
            direction=_score_to_direction(score), confidence=1.0, note=note
        ), _last_bar_date(crude)))
    else:
        out.append(PreMarketSignal(name="Crude Oil", score=0, weight=0.034, raw_value="N/A", direction="Neutral", confidence=0))
    return out


# ─── Crypto + Mega-cap (5%): BTC, ETH, AAPL, MSFT, NVDA ─────────────────────
def _fetch_crypto_megacap() -> list[PreMarketSignal]:
    out = []
    tickers = [("BTC-USD", "Bitcoin", 0.015), ("ETH-USD", "Ethereum", 0.01), ("AAPL", "AAPL", 0.008), ("MSFT", "MSFT", 0.007), ("NVDA", "NVDA", 0.01)]
    for sym, label, w in tickers:
        if sym.endswith("-USD"):
            close = fetch_ohlcv_safe(sym, "5d")
            prev, last = _prior_and_last(close)
            pct = _pct(prev, last) if (prev and last) else None
            bar_d = _last_bar_date(close)
        else:
            pct, bar_d = _us_listed_move(sym)
        if pct is None:
            out.append(PreMarketSignal(name=label, score=0, weight=w, raw_value="N/A", direction="Neutral", confidence=0))
            continue
        score = max(-1, min(1, pct / 2.0))
        out.append(_mark_stale(PreMarketSignal(
            name=label, score=score, weight=w, raw_value=f"{pct:+.2f}%",
            direction=_score_to_direction(score), confidence=1.0
        ), bar_d))
        time.sleep(0.2)
    return out


def _confidence_weighted_composite(signals: list[PreMarketSignal]) -> tuple[float, float]:
    """Only signals with confidence > 0 participate. Returns (composite_score, confidence)."""
    total_w = 0.0
    weighted_sum = 0.0
    for s in signals:
        if s.confidence > 0:
            w = s.weight * s.confidence
            total_w += w
            weighted_sum += s.score * w
    if total_w <= 0:
        return 0.0, 0.0
    composite = weighted_sum / total_w
    composite = max(-1, min(1, composite))
    conf = min(1.0, total_w)
    return composite, conf


def _score_to_bias(score: float) -> Bias:
    if score >= 0.5:
        return Bias.STRONG_BULL
    if score >= 0.25:
        return Bias.BULL
    if score >= 0.08:
        return Bias.SLIGHT_BULL
    if score >= -0.08:
        return Bias.NEUTRAL
    if score >= -0.25:
        return Bias.SLIGHT_BEAR
    if score >= -0.5:
        return Bias.BEAR
    return Bias.STRONG_BEAR


def _minutes_to_open_est() -> int:
    from datetime import datetime
    try:
        import pytz
        est = pytz.timezone("America/New_York")
        now = datetime.now(est)
        if now.weekday() >= 5:
            return 0
        open_at = now.replace(hour=9, minute=30, second=0, microsecond=0)
        if now >= open_at:
            return 0
        delta = open_at - now
        return int(delta.total_seconds() / 60)
    except Exception:
        return 0


def _top_drivers(signals: list[PreMarketSignal], n: int = 3) -> tuple[list[str], list[str]]:
    with_data = [s for s in signals if s.confidence > 0]
    bullish = sorted([s for s in with_data if s.score > 0.1], key=lambda x: -x.score)[:n]
    bearish = sorted([s for s in with_data if s.score < -0.1], key=lambda x: x.score)[:n]
    def fmt(s: PreMarketSignal) -> str:
        return f"{s.name}: {s.raw_value}"
    return [fmt(s) for s in bullish], [fmt(s) for s in bearish]


def _key_risks(signals: list[PreMarketSignal], composite: float) -> list[str]:
    risks = []
    vix = next((s for s in signals if "VIX" in s.name), None)
    if vix and vix.confidence > 0 and vix.score < -0.3:
        risks.append("VIX elevated or rising — volatility headwind.")
    if composite < -0.2:
        risks.append("Pre-market composite bearish — consider reducing size into open.")
    return risks


def _sector_plays(signals: list[PreMarketSignal]) -> dict[str, list[str]]:
    plays = {}
    oil = next((s for s in signals if "Crude" in s.name), None)
    if oil and oil.confidence > 0 and oil.score > 0.2:
        plays["Energy (oil signal)"] = ["XLE", "XOM"]
    if oil and oil.confidence > 0 and oil.score < -0.3:
        plays["Avoid energy (oil stress)"] = ["XLE"]
    return plays


class PreMarketEngine:
    """Runs all 6 categories, 15 sources; returns PreMarketReport with confidence-weighted composite."""

    def run(self, verbose: bool = True) -> PreMarketReport:
        from signals.time_et import now_et

        ts = now_et()

        all_signals: list[PreMarketSignal] = []
        fetchers = [
            _fetch_futures,
            _fetch_international,
            _fetch_volatility,
            _fetch_rates,
            _fetch_currencies,
            _fetch_commodities,
            _fetch_crypto_megacap,
        ]
        with ThreadPoolExecutor(max_workers=len(fetchers)) as ex:
            futures = {ex.submit(fn): fn.__name__ for fn in fetchers}
            for fut in as_completed(futures):
                try:
                    all_signals.extend(fut.result())
                except Exception:
                    pass

        composite, confidence = _confidence_weighted_composite(all_signals)
        bias = _score_to_bias(composite)
        top_bull, top_bear = _top_drivers(all_signals)
        risks = _key_risks(all_signals, composite)
        sector_plays = _sector_plays(all_signals)

        return PreMarketReport(
            timestamp=ts,
            composite_score=round(composite, 4),
            bias=bias,
            confidence=round(confidence, 3),
            minutes_to_open=_minutes_to_open_est(),
            top_bullish=top_bull,
            top_bearish=top_bear,
            key_risks=risks,
            suggested_tickers=sector_plays,
            signals=all_signals,
        )
