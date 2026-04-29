from __future__ import annotations

import hashlib
import logging
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Optional

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    from backports.zoneinfo import ZoneInfo  # type: ignore

from scanner.store import ScannerStore
from scanner.ticker_universe import (
    AlertType,
    RELATED_TICKERS,
    SURFACING_THRESHOLDS,
    ScanPriority,
    ScanTier,
    SurfacingThreshold,
)

logger = logging.getLogger("scanner")
ET = ZoneInfo("America/New_York")


@dataclass
class MarketSnapshot:
    symbol: str
    price: float
    price_change_pct: float
    regime: str
    regime_confidence: float
    iv_rank: float
    iv_percentile: float
    call_put_flow_ratio: float
    er_days_away: Optional[int]
    vix: float
    atr_pct: float
    support_level: Optional[float]
    kelly_base: float
    in_watchlist: bool
    scan_tier: ScanTier
    sector: str
    as_of: str = field(default_factory=lambda: datetime.now().isoformat())
    # Optional: short-term ML prob (0-100) for ML_PROB_CROSSED alert
    ml_prob_short: Optional[float] = None


@dataclass
class ScanAlert:
    id: str
    type: AlertType
    ticker: Optional[str]
    priority: ScanPriority
    headline: str
    body: str
    risk_level: str
    color: str
    emoji: str
    timestamp: str
    signals: dict
    scan_tier: ScanTier
    surface_to_all: bool
    ttl_minutes: int = 60
    dismissed: bool = False
    # Plain-language entry/exit/duration so alerts are actionable
    actionable: Optional[str] = None
    # Compact quick-summary line for alert cards
    one_liner: Optional[str] = None
    # Disambiguate ST vs MT vs LT for dedupe/cooldown (same AlertType, different horizon band)
    dedupe_extra: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


ALERT_COLORS = {
    AlertType.MACRO_RISK_OFF: "#EF4444",
    AlertType.MACRO_RISK_ON: "#10B981",
    AlertType.ER_LOTTO: "#F59E0B",
    AlertType.ER_IV_CRUSH: "#F59E0B",
    AlertType.COVERED_CALL: "#10B981",
    AlertType.CREDIT_SPREAD: "#3B82F6",
    AlertType.MOMENTUM_BREAKOUT: "#8B5CF6",
    AlertType.SUPPORT_BOUNCE: "#8B5CF6",
    AlertType.KELLY_REDUCTION: "#EF4444",
    AlertType.OPTIONS_FLOW_SPIKE: "#06B6D4",
    AlertType.REGIME_CHANGE: "#F59E0B",
    AlertType.EARNINGS_SOON: "#F59E0B",
    AlertType.ENTRY_ZONE_ENTERED: "#10B981",
    AlertType.STOP_HIT: "#EF4444",
    AlertType.STOP_APPROACHING: "#F59E0B",
    AlertType.TARGET_HIT: "#10B981",
    AlertType.TARGET_APPROACHING: "#FBBF24",
    AlertType.ML_PROB_CROSSED: "#3B82F6",
}

ALERT_EMOJIS = {
    AlertType.MACRO_RISK_OFF: "🔴",
    AlertType.MACRO_RISK_ON: "🟢",
    AlertType.ER_LOTTO: "🟡",
    AlertType.ER_IV_CRUSH: "🟡",
    AlertType.COVERED_CALL: "🟢",
    AlertType.CREDIT_SPREAD: "🔵",
    AlertType.MOMENTUM_BREAKOUT: "🔺",
    AlertType.SUPPORT_BOUNCE: "🔺",
    AlertType.KELLY_REDUCTION: "🔴",
    AlertType.OPTIONS_FLOW_SPIKE: "⚡",
    AlertType.REGIME_CHANGE: "🔄",
    AlertType.EARNINGS_SOON: "📅",
    AlertType.ENTRY_ZONE_ENTERED: "✅",
    AlertType.STOP_HIT: "🛑",
    AlertType.STOP_APPROACHING: "⚠️",
    AlertType.TARGET_HIT: "🎯",
    AlertType.TARGET_APPROACHING: "✂️",
    AlertType.ML_PROB_CROSSED: "📈",
}


def _alert_id(ticker: Optional[str], alert_type: AlertType, suffix: str = "") -> str:
    raw = f"{ticker or 'MACRO'}:{alert_type}:{suffix}:{datetime.now().strftime('%Y%m%d%H%M')}"
    return hashlib.md5(raw.encode()).hexdigest()[:12]


def _actionable_for_alert(snap: MarketSnapshot, alert_type: AlertType) -> str:
    """Plain-language entry, exit, and duration so the alert is actionable."""
    price = snap.price
    support = snap.support_level
    er_days = snap.er_days_away
    today = datetime.now(tz=ET).strftime("%b %d")
    support_str = f"${support:.2f}" if support and support > 0 else "recent support"
    if alert_type == AlertType.SUPPORT_BOUNCE:
        exit_hint = f"Exit if price breaks below {support_str}" if support else "Exit on break of support"
        return (
            f"Entry: consider buying near current price ${price:.2f} (today) or on a pullback to {support_str}. "
            f"Exit: take profit at 3–5% upside, or {exit_hint}. "
            f"Duration: 1–4 weeks."
        )
    if alert_type == AlertType.OPTIONS_FLOW_SPIKE:
        stop_hint = f"Set a mental stop below {support_str}." if support else "Set a stop based on your risk."
        return (
            f"Entry: if trading options, use current stock price ${price:.2f} as reference (as of today). "
            f"{stop_hint} "
            f"Duration: review in 1–2 weeks; close or roll before earnings if within 2 weeks."
        )
    if alert_type == AlertType.COVERED_CALL:
        return (
            f"Entry: sell a call at or above current price ${price:.2f} (today). "
            f"Collect premium; typical duration 30–45 days to expiry. "
            f"Exit: buy back if stock drops sharply, or let expire / get assigned."
        )
    if alert_type == AlertType.CREDIT_SPREAD:
        return (
            f"Entry: consider selling a put or call spread with current price ${price:.2f} as reference. "
            f"Duration: 30–45 DTE. Exit: close at 50% profit or before earnings."
        )
    if alert_type == AlertType.MOMENTUM_BREAKOUT:
        return (
            f"Entry: only if you chase momentum; current price ${price:.2f}. "
            f"Use a tight stop (e.g. below {support_str}). Duration: days to 2 weeks."
        )
    if alert_type == AlertType.ER_LOTTO and er_days is not None:
        return (
            f"High risk. Entry: only if you accept lottery risk; current price ${price:.2f}. "
            f"Exit before or at earnings (in {er_days} days). Duration: until earnings."
        )
    if alert_type == AlertType.ER_IV_CRUSH:
        return (
            f"Entry: sell premium (e.g. credit spread or iron condor) with earnings in view. "
            f"Exit before earnings to avoid event risk. Duration: until earnings."
        )
    # Default: at least give price and date
    return f"Reference price ${price:.2f} as of {today}. Check chart for entry and set your own stop and target."


def _snapshot_one_liner(snap: MarketSnapshot) -> str:
    """Compact summary in: Bias + probability + expected range."""
    return _bias_prob_range_line(
        price=snap.price,
        atr_pct=snap.atr_pct,
        regime=snap.regime,
        regime_confidence=snap.regime_confidence,
        prob_override=snap.ml_prob_short,
    )


def _bias_from_regime(regime: str) -> str:
    r = (regime or "").upper()
    if "BULL" in r:
        return "Bullish"
    if "BEAR" in r:
        return "Bearish"
    return "Neutral"


def _bias_prob_range_line(
    *,
    price: float,
    atr_pct: float,
    regime: str,
    regime_confidence: float | None = None,
    prob_override: float | None = None,
    earnings_move_pct: float | None = None,
    earnings_hit_rate: float | None = None,
    earnings_events: int | None = None,
) -> str:
    bias = _bias_from_regime(regime)
    prob = (
        float(prob_override)
        if prob_override is not None
        else float(regime_confidence or 50.0)
    )
    prob = max(0.0, min(100.0, prob))
    exp_move_pct = max(float(atr_pct or 0.0) * 0.65, 0.6)
    lo = float(price) * (1.0 - exp_move_pct / 100.0)
    hi = float(price) * (1.0 + exp_move_pct / 100.0)
    if earnings_move_pct is not None and earnings_move_pct > 0:
        e_seg = f"Earnings +/-{float(earnings_move_pct):.1f}%"
        if earnings_hit_rate is not None and earnings_events is not None and earnings_events > 0:
            e_seg += f" | Backtest {float(earnings_hit_rate):.0f}% ({int(earnings_events)} evts)"
        return f"{bias} {prob:.0f}% | {e_seg} | Range ${lo:.2f}–${hi:.2f}"
    return f"{bias} {prob:.0f}% | Range ${lo:.2f}–${hi:.2f}"


def _earnings_target_for_alert(
    ticker: str,
    snap: MarketSnapshot,
    state_row: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Best-effort earnings target summary for one-liner alerts.
    Uses same model output as ticker detail price-targets; caches in retail state row.
    """
    st = state_row if isinstance(state_row, dict) else {}
    cached = st.get("earnings_target_cache")
    if isinstance(cached, dict):
        return cached
    out: dict[str, Any] = {}
    try:
        from config_loader import load_config
        from signals.price_targets import run_price_targets

        pt = run_price_targets(
            ticker=ticker,
            market_regime=(snap.regime or "NEUTRAL"),
            config=load_config(),
        )
        et = pt.get("earnings_target") if isinstance(pt, dict) else None
        if isinstance(et, dict):
            out = {
                "expected_move_pct": et.get("expected_move_pct"),
                "calibration_hit_rate": (
                    float(et.get("calibration_hit_rate")) * 100.0
                    if et.get("calibration_hit_rate") is not None
                    else None
                ),
                "backtest_events": et.get("backtest_events") or et.get("historical_events"),
            }
    except Exception as e:
        logger.debug("earnings target summary unavailable for %s: %s", ticker, e)
    st["earnings_target_cache"] = out
    return out


def _entry_zone_actionable(band_key: str, entry_low: float, entry_high: float, price: float) -> bool:
    """
    Filter out "always-in-zone" ranges that are too wide to be actionable.
    Prevents alerts like SPY long-term zones spanning huge portions of spot.
    """
    if not (entry_low > 0 and entry_high > entry_low and price > 0):
        return False
    width_pct_of_spot = (entry_high - entry_low) / price
    max_width_by_band = {
        "short": 0.14,   # <= 14% of spot
        "medium": 0.30,  # <= 30% of spot
        "long": 0.45,    # <= 45% of spot
    }
    max_width = max_width_by_band.get(str(band_key).lower(), 0.30)
    return width_pct_of_spot <= max_width


def _risk_level(snap: MarketSnapshot, alert_type: AlertType) -> str:
    if alert_type == AlertType.ER_LOTTO:
        return "EXTREME"
    score = 0
    if snap.vix > 25:
        score += 2
    elif snap.vix > 20:
        score += 1
    if snap.iv_rank > 80:
        score += 2
    elif snap.iv_rank > 60:
        score += 1
    if snap.er_days_away is not None and snap.er_days_away <= 3:
        score += 2
    if snap.atr_pct > 4:
        score += 1
    if "BEAR" in snap.regime:
        score += 1
    if score >= 5:
        return "HIGH"
    if score >= 3:
        return "MODERATE"
    return "LOW"


class SignalEvaluator:
    def evaluate(self, snap: MarketSnapshot, macro_flag: str, user_watchlist: set[str]) -> list[ScanAlert]:
        out: list[ScanAlert] = []
        in_watchlist = snap.symbol in user_watchlist
        for alert_type, threshold in SURFACING_THRESHOLDS.items():
            if alert_type in (AlertType.MACRO_RISK_OFF, AlertType.MACRO_RISK_ON):
                continue
            if self._passes(snap, alert_type, threshold, macro_flag, in_watchlist):
                out.append(self._build_alert(snap, alert_type, macro_flag, in_watchlist))
        return out

    def _passes(
        self,
        snap: MarketSnapshot,
        alert_type: AlertType,
        threshold: SurfacingThreshold,
        macro_flag: str,
        in_watchlist: bool,
    ) -> bool:
        if macro_flag == "RISK_OFF" and alert_type in (
            AlertType.ER_LOTTO,
            AlertType.COVERED_CALL,
            AlertType.MOMENTUM_BREAKOUT,
            AlertType.CREDIT_SPREAD,
        ):
            if not in_watchlist or snap.iv_rank < 80:
                return False

        if not (threshold.min_iv_rank <= snap.iv_rank <= threshold.max_iv_rank):
            return False

        if alert_type == AlertType.OPTIONS_FLOW_SPIKE:
            if not (
                snap.call_put_flow_ratio >= threshold.min_flow_ratio
                or snap.call_put_flow_ratio <= (1 / threshold.min_flow_ratio)
            ):
                return False
        else:
            if not (threshold.min_flow_ratio <= snap.call_put_flow_ratio <= threshold.max_flow_ratio):
                return False

        if threshold.max_er_days is not None:
            if snap.er_days_away is None or snap.er_days_away > threshold.max_er_days:
                return False
        if threshold.min_er_days is not None:
            if snap.er_days_away is not None and snap.er_days_away < threshold.min_er_days:
                return False

        if threshold.bullish_regime_req and snap.regime not in ("BULLISH", "STRONGLY_BULLISH"):
            return False
        if threshold.bearish_regime_req and snap.regime not in ("BEARISH", "STRONGLY_BEARISH"):
            return False
        if snap.regime_confidence < threshold.min_regime_conf:
            return False

        if snap.price_change_pct < threshold.min_price_change_pct:
            return False
        if snap.price < threshold.min_price:
            return False
        if snap.atr_pct > threshold.max_atr_pct:
            return False
        if not threshold.surface_to_all and not in_watchlist:
            return False
        return True

    def _build_alert(self, snap: MarketSnapshot, alert_type: AlertType, macro_flag: str, in_watchlist: bool) -> ScanAlert:
        risk = _risk_level(snap, alert_type)
        if in_watchlist and risk in ("HIGH", "EXTREME"):
            pr = ScanPriority.CRITICAL
        elif in_watchlist:
            pr = ScanPriority.HIGH
        else:
            pr = ScanPriority.MEDIUM

        headline = f"{snap.symbol} {alert_type.value.replace('_',' ').title()}"
        if alert_type == AlertType.ER_LOTTO and snap.er_days_away is not None:
            headline = f"{snap.symbol} ER Lotto — {snap.er_days_away}d Away"
        if alert_type == AlertType.MOMENTUM_BREAKOUT:
            headline = f"{snap.symbol} Momentum Breakout +{snap.price_change_pct:.1f}%"

        body = f"IV Rank {snap.iv_rank:.0f}, flow {snap.call_put_flow_ratio:.1f}x, regime {snap.regime} ({snap.regime_confidence:.0f}%)."
        actionable = _actionable_for_alert(snap, alert_type)

        return ScanAlert(
            id=_alert_id(snap.symbol, alert_type),
            type=alert_type,
            ticker=snap.symbol,
            priority=pr,
            headline=headline,
            body=body,
            risk_level=risk,
            color=ALERT_COLORS.get(alert_type, "#94A3B8"),
            emoji=ALERT_EMOJIS.get(alert_type, "🔔"),
            timestamp=datetime.now().isoformat(),
            signals={
                "ivRank": snap.iv_rank,
                "flowRatio": snap.call_put_flow_ratio,
                "regime": snap.regime,
                "regimeConf": snap.regime_confidence,
                "erDaysAway": snap.er_days_away,
                "vix": snap.vix,
                "priceChangePct": snap.price_change_pct,
                "macroFlag": macro_flag,
                "price": snap.price,
                "supportLevel": snap.support_level,
            },
            scan_tier=snap.scan_tier,
            surface_to_all=SURFACING_THRESHOLDS[alert_type].surface_to_all,
            actionable=actionable,
            one_liner=_snapshot_one_liner(snap),
            dedupe_extra=None,
        )


def _build_retail_alert(
    ticker: str,
    alert_type: AlertType,
    headline: str,
    body: str,
    scan_tier: ScanTier,
    signals: dict[str, Any],
    actionable: Optional[str] = None,
    one_liner: Optional[str] = None,
    dedupe_extra: Optional[str] = None,
) -> ScanAlert:
    """Build a retail quick-decision alert with one-line plain English and optional actionable text."""
    pr = ScanPriority.HIGH if alert_type in (
        AlertType.ENTRY_ZONE_ENTERED,
        AlertType.STOP_HIT,
        AlertType.ML_PROB_CROSSED,
    ) else ScanPriority.MEDIUM
    return ScanAlert(
        id=_alert_id(ticker, alert_type, dedupe_extra or ""),
        type=alert_type,
        ticker=ticker,
        priority=pr,
        headline=headline,
        body=body,
        risk_level="MODERATE",
        color=ALERT_COLORS.get(alert_type, "#94A3B8"),
        emoji=ALERT_EMOJIS.get(alert_type, "🔔"),
        timestamp=datetime.now().isoformat(),
        signals=signals,
        scan_tier=scan_tier,
        surface_to_all=True,
        actionable=actionable,
        one_liner=one_liner,
        dedupe_extra=dedupe_extra,
    )


def evaluate_retail_alerts(
    snaps: list[MarketSnapshot],
    horizon_levels: dict[str, dict[str, Any]],
    state: dict[str, dict[str, Any]],
    ml_probs: dict[str, float],
    watchlist: set[str],
    *,
    enable_band: bool = True,
    enable_earnings: bool = True,
    enable_ml_prob: bool = True,
    trim_approach_fraction: float = 0.95,
) -> tuple[list[ScanAlert], dict[str, dict[str, Any]]]:
    """
    Retail alerts: EARNINGS_SOON; per ST/MT/LT band — ENTRY_ZONE_ENTERED, STOP_*, TARGET_APPROACHING (trim),
    TARGET_HIT; ML_PROB_CROSSED.
    """
    from scanner.horizon_levels import (
        EARNINGS_SOON_DAYS,
        ML_PROB_CROSS_THRESHOLD,
        normalize_ticker_levels,
    )

    alerts: list[ScanAlert] = []
    new_state: dict[str, dict[str, Any]] = dict(state)
    tf = max(0.5, min(0.999, float(trim_approach_fraction)))

    for snap in snaps:
        ticker = snap.symbol
        price = snap.price
        in_wl = ticker in watchlist
        st = new_state.get(ticker) or {}
        last_price = st.get("last_price")
        prev_ml = st.get("previous_ml_prob")

        # EARNINGS_SOON — only for watchlist
        if enable_earnings and in_wl and snap.er_days_away is not None and snap.er_days_away in EARNINGS_SOON_DAYS:
            ed = snap.er_days_away
            et = _earnings_target_for_alert(ticker, snap, st)
            e_move = et.get("expected_move_pct")
            e_hit = et.get("calibration_hit_rate")
            e_n = et.get("backtest_events")
            alerts.append(_build_retail_alert(
                ticker,
                AlertType.EARNINGS_SOON,
                f"{ticker} earnings in {ed} day(s)",
                f"Reduce size or wait for post-earnings reaction. Earnings in {ed} days.",
                snap.scan_tier,
                {
                    "erDaysAway": ed,
                    "price": price,
                    "earningsExpectedMovePct": e_move,
                    "earningsBacktestHitRatePct": e_hit,
                    "earningsBacktestEvents": e_n,
                },
                actionable=(
                    f"Do not open new positions until after earnings (in {ed} days). "
                    f"If you already hold, reduce size or hedge by then. "
                    f"Exit any speculative position before the report. Current price ${price:.2f}."
                ),
                one_liner=_bias_prob_range_line(
                    price=price,
                    atr_pct=snap.atr_pct,
                    regime=snap.regime,
                    regime_confidence=snap.regime_confidence,
                    prob_override=snap.ml_prob_short,
                    earnings_move_pct=float(e_move) if e_move is not None else None,
                    earnings_hit_rate=float(e_hit) if e_hit is not None else None,
                    earnings_events=int(e_n) if e_n is not None else None,
                ),
                dedupe_extra="earnings",
            ))

        raw_levels = horizon_levels.get(ticker)
        bands = normalize_ticker_levels(raw_levels) if enable_band else {}

        for band_key, levels in bands.items():
            el = float(levels.get("entry_low") or 0)
            eh = float(levels.get("entry_high") or 0)
            stop = float(levels.get("stop_loss") or 0)
            target = float(levels.get("target") or 0)
            label = str(levels.get("horizon_label") or band_key.upper())
            zone_flag = f"was_in_entry_zone_{band_key}"
            was_in_zone = bool(st.get(zone_flag, False))
            in_zone = el <= price <= eh if (el and eh) else False
            actionable_zone = in_zone and _entry_zone_actionable(band_key, el, eh, price)
            dex = band_key

            if el and eh and actionable_zone and not was_in_zone:
                act = (
                    f"Entry: buy in range ${el:.2f}–${eh:.2f} (current ${price:.2f}). "
                    f"Exit: use stop ${stop:.2f} and target ${target:.2f}. "
                    f"Duration: hold until target or stop hit."
                ) if (stop and target) else (
                    f"Entry: buy in range ${el:.2f}–${eh:.2f} (current ${price:.2f}). Set your own stop and target."
                )
                alerts.append(_build_retail_alert(
                    ticker,
                    AlertType.ENTRY_ZONE_ENTERED,
                    f"{ticker} in {label} buy zone ${el:.2f}–${eh:.2f}",
                    f"Price in buy zone ({band_key}). Consider adding per your plan.",
                    snap.scan_tier,
                    {
                        "band": band_key,
                        "entryLow": el,
                        "entryHigh": eh,
                        "price": price,
                        "stopLoss": stop,
                        "target": target,
                    },
                    actionable=act,
                    one_liner=_bias_prob_range_line(
                        price=price,
                        atr_pct=snap.atr_pct,
                        regime=snap.regime,
                        regime_confidence=snap.regime_confidence,
                        prob_override=snap.ml_prob_short,
                    ),
                    dedupe_extra=dex,
                ))
            if stop and price < stop:
                alerts.append(_build_retail_alert(
                    ticker,
                    AlertType.STOP_HIT,
                    f"{ticker} ({label}) below stop ${stop:.2f}",
                    f"Price below {band_key} stop — consider exit or trim.",
                    snap.scan_tier,
                    {"band": band_key, "stopLoss": stop, "price": price},
                    actionable=(
                        f"Exit: price ${price:.2f} is below {band_key} stop ${stop:.2f}. "
                        f"Trim or close now to limit loss."
                    ),
                    one_liner=_bias_prob_range_line(
                        price=price,
                        atr_pct=snap.atr_pct,
                        regime=snap.regime,
                        regime_confidence=snap.regime_confidence,
                        prob_override=snap.ml_prob_short,
                    ),
                    dedupe_extra=dex,
                ))
            elif stop and price > stop and price <= stop * 1.02:
                alerts.append(_build_retail_alert(
                    ticker,
                    AlertType.STOP_APPROACHING,
                    f"{ticker} ({label}) within 2% of stop ${stop:.2f}",
                    f"Price near {band_key} stop. Decide: hold or trim.",
                    snap.scan_tier,
                    {"band": band_key, "stopLoss": stop, "price": price},
                    actionable=(
                        f"Price ${price:.2f} is near {band_key} stop ${stop:.2f}. "
                        f"Decide within 1–2 days: hold or trim before stop is hit."
                    ),
                    one_liner=_bias_prob_range_line(
                        price=price,
                        atr_pct=snap.atr_pct,
                        regime=snap.regime,
                        regime_confidence=snap.regime_confidence,
                        prob_override=snap.ml_prob_short,
                    ),
                    dedupe_extra=dex,
                ))
            if target and price >= target:
                alerts.append(_build_retail_alert(
                    ticker,
                    AlertType.TARGET_HIT,
                    f"{ticker} ({label}) reached target ${target:.2f}",
                    f"Target hit — consider taking profit or trimming.",
                    snap.scan_tier,
                    {"band": band_key, "target": target, "price": price},
                    actionable=(
                        f"Exit: {band_key} target ${target:.2f} reached (price ${price:.2f}). "
                        f"Consider taking profit or scaling out."
                    ),
                    one_liner=_bias_prob_range_line(
                        price=price,
                        atr_pct=snap.atr_pct,
                        regime=snap.regime,
                        regime_confidence=snap.regime_confidence,
                        prob_override=snap.ml_prob_short,
                    ),
                    dedupe_extra=dex,
                ))
            elif target and tf < 1 and price >= tf * target:
                alerts.append(_build_retail_alert(
                    ticker,
                    AlertType.TARGET_APPROACHING,
                    f"{ticker} ({label}) near target ${target:.2f} — consider trim",
                    f"Within {(1 - tf) * 100:.0f}% of {band_key} target; good zone to scale out partially.",
                    snap.scan_tier,
                    {"band": band_key, "target": target, "price": price, "trimFraction": tf},
                    actionable=(
                        f"Price ${price:.2f} is near {band_key} target ${target:.2f}. "
                        f"Consider trimming a portion or tightening stops."
                    ),
                    one_liner=_bias_prob_range_line(
                        price=price,
                        atr_pct=snap.atr_pct,
                        regime=snap.regime,
                        regime_confidence=snap.regime_confidence,
                        prob_override=snap.ml_prob_short,
                    ),
                    dedupe_extra=dex,
                ))

            st = {**st, zone_flag: actionable_zone}

        st = {**st, "last_price": price}
        new_state[ticker] = st

        # ML_PROB_CROSSED — need current and previous ML prob
        ml_current = ml_probs.get(ticker) if ml_probs else (snap.ml_prob_short if getattr(snap, "ml_prob_short", None) is not None else None)
        if enable_ml_prob and in_wl and ml_current is not None:
            prev = prev_ml if prev_ml is not None else st.get("previous_ml_prob")
            if prev is not None and float(prev) < ML_PROB_CROSS_THRESHOLD <= float(ml_current):
                alerts.append(_build_retail_alert(
                    ticker,
                    AlertType.ML_PROB_CROSSED,
                    f"{ticker} ML prob now {ml_current:.0f}% (crossed {ML_PROB_CROSS_THRESHOLD:.0f}%)",
                    f"Model now supports add. Consider adding on pullbacks.",
                    snap.scan_tier,
                    {"mlProb": ml_current, "previousMlProb": prev, "threshold": ML_PROB_CROSS_THRESHOLD, "price": price},
                    actionable=(
                        f"Entry: model supports adding at current price ${price:.2f}; consider on pullbacks. "
                        f"Set your own stop and target. Duration: medium term (weeks)."
                    ),
                    one_liner=_bias_prob_range_line(
                        price=price,
                        atr_pct=snap.atr_pct,
                        regime=snap.regime,
                        regime_confidence=snap.regime_confidence,
                        prob_override=float(ml_current),
                    ),
                    dedupe_extra="ml",
                ))
            st = {**new_state.get(ticker, st), "previous_ml_prob": ml_current}
            new_state[ticker] = st

        # Keep last_price for tickers that didn't have levels
        if ticker not in new_state and (last_price is not None or price):
            new_state[ticker] = {**st, "last_price": price}

    return alerts, new_state


class AlertDeduplicator:
    def __init__(self):
        self._last: dict[tuple[str, AlertType, str], datetime] = {}
        self.cooldowns_min: dict[AlertType, int] = {
            AlertType.ER_LOTTO: 120,
            AlertType.ER_IV_CRUSH: 240,
            AlertType.COVERED_CALL: 180,
            AlertType.CREDIT_SPREAD: 120,
            AlertType.MOMENTUM_BREAKOUT: 30,
            AlertType.SUPPORT_BOUNCE: 60,
            AlertType.OPTIONS_FLOW_SPIKE: 45,
            AlertType.REGIME_CHANGE: 240,
            AlertType.MACRO_RISK_OFF: 60,
            AlertType.MACRO_RISK_ON: 60,
            AlertType.KELLY_REDUCTION: 120,
            AlertType.EARNINGS_SOON: 360,  # 6h per ticker
            AlertType.ENTRY_ZONE_ENTERED: 120,
            AlertType.STOP_HIT: 60,
            AlertType.STOP_APPROACHING: 60,
            AlertType.TARGET_HIT: 120,
            AlertType.TARGET_APPROACHING: 90,
            AlertType.ML_PROB_CROSSED: 180,
        }

    def is_dup(self, ticker: str, t: AlertType, extra: str = "") -> bool:
        key = (ticker, t, extra or "")
        last = self._last.get(key)
        if not last:
            return False
        cd = self.cooldowns_min.get(t, 60)
        return (datetime.now() - last).total_seconds() < cd * 60

    def record(self, ticker: str, t: AlertType, extra: str = "") -> None:
        self._last[(ticker, t, extra or "")] = datetime.now()

    def prune(self) -> None:
        cutoff = datetime.now() - timedelta(hours=12)
        self._last = {k: v for k, v in self._last.items() if v >= cutoff}  # type: ignore[assignment]


class MarketHours:
    @classmethod
    def _now(cls) -> datetime:
        return datetime.now(tz=ET)

    @classmethod
    def is_scan_active(cls) -> bool:
        now = cls._now()
        if now.weekday() >= 5:
            return False
        m = now.hour * 60 + now.minute
        return 480 <= m <= 960  # 8:00–16:00 ET

    @classmethod
    def scan_interval_seconds(cls) -> int:
        now = cls._now()
        if now.weekday() >= 5:
            return 60 * 30
        m = now.hour * 60 + now.minute
        if 480 <= m < 570:
            return 60 * 15
        if 570 <= m <= 960:
            return 60 * 30
        return 60 * 30


def _load_scanner_alert_settings() -> tuple[bool, dict[str, Any]]:
    """Defaults: options-style IV/flow surfacing off; band + earnings + ML on."""
    try:
        from config_loader import load_config

        a = load_config().get("alerts") or {}
        enable_options = bool(a.get("enable_options_alerts", False))
        retail = {
            "enable_band_alerts": a.get("enable_band_alerts", True),
            "enable_earnings_alerts": a.get("enable_earnings_alerts", True),
            "enable_ml_prob_alerts": a.get("enable_ml_prob_alerts", True),
            "trim_approach_fraction": float(a.get("trim_approach_fraction", 0.95)),
            "cooldown_overrides": a.get("retail_cooldown_min") or {},
        }
        return enable_options, retail
    except Exception:
        return False, {
            "enable_band_alerts": True,
            "enable_earnings_alerts": True,
            "enable_ml_prob_alerts": True,
            "trim_approach_fraction": 0.95,
            "cooldown_overrides": {},
        }


class ScanEngine:
    def __init__(self):
        self.eval = SignalEvaluator()
        self.dedupe = AlertDeduplicator()
        self._stats = {
            "total_scans": 0,
            "total_alerts": 0,
            "total_surfaced": 0,
            "last_scan_at": None,
            "errors": [],
        }
        self._count = 0

    def run(
        self,
        *,
        snaps: list[MarketSnapshot],
        macro_flag: str,
        watchlist: set[str],
        on_alert: Callable[[ScanAlert], None],
        data_root: Optional[Path] = None,
        enable_options_alerts: Optional[bool] = None,
        retail_config: Optional[dict[str, Any]] = None,
    ) -> dict:
        started = datetime.now()
        generated = 0
        surfaced = 0
        errs: list[str] = []
        opt_def, rc_def = _load_scanner_alert_settings()
        if enable_options_alerts is None:
            enable_options_alerts = opt_def
        rc = retail_config if retail_config is not None else rc_def
        enable_band = rc.get("enable_band_alerts", True)
        enable_earnings = rc.get("enable_earnings_alerts", True)
        enable_ml = rc.get("enable_ml_prob_alerts", True)
        trim_frac = float(rc.get("trim_approach_fraction", 0.95))  # alert "consider trim" when price >= frac * target
        for _at_name, _mins in (rc.get("cooldown_overrides") or {}).items():
            try:
                _at = AlertType[_at_name]
                self.dedupe.cooldowns_min[_at] = int(_mins)
            except Exception:
                pass

        for s in snaps:
            try:
                alerts = self.eval.evaluate(s, macro_flag, watchlist) if enable_options_alerts else []
                generated += len(alerts)
                for a in alerts:
                    ex = a.dedupe_extra or ""
                    if self.dedupe.is_dup(a.ticker or "?", a.type, ex):
                        continue
                    self.dedupe.record(a.ticker or "?", a.type, ex)
                    on_alert(a)
                    surfaced += 1
            except Exception as e:
                errs.append(f"{s.symbol}: {e}")

        # Retail quick-decision alerts (EARNINGS_SOON, ENTRY_ZONE_ENTERED, STOP_HIT, TARGET_HIT, ML_PROB_CROSSED)
        if data_root:
            try:
                from scanner.horizon_levels import (
                    read_horizon_levels,
                    read_retail_alert_state,
                    read_ml_probs,
                    write_retail_alert_state,
                )
                levels = read_horizon_levels(data_root)
                state = read_retail_alert_state(data_root)
                ml_probs = read_ml_probs(data_root)
                retail_alerts, new_state = evaluate_retail_alerts(
                    snaps,
                    levels,
                    state,
                    ml_probs,
                    watchlist,
                    enable_band=enable_band,
                    enable_earnings=enable_earnings,
                    enable_ml_prob=enable_ml,
                    trim_approach_fraction=trim_frac,
                )
                write_retail_alert_state(data_root, new_state)
                generated += len(retail_alerts)
                for a in retail_alerts:
                    ex = a.dedupe_extra or ""
                    if self.dedupe.is_dup(a.ticker or "?", a.type, ex):
                        continue
                    self.dedupe.record(a.ticker or "?", a.type, ex)
                    on_alert(a)
                    surfaced += 1
            except Exception as e:
                logger.debug("retail alerts failed: %s", e)
                errs.append(f"retail_alerts: {e}")

        self._count += 1
        if self._count % 20 == 0:
            self.dedupe.prune()
        self._stats["total_scans"] += 1
        self._stats["total_alerts"] += generated
        self._stats["total_surfaced"] += surfaced
        self._stats["last_scan_at"] = datetime.now().isoformat()
        if errs:
            self._stats["errors"] = (self._stats.get("errors") or [])[-50:] + errs
        return {
            "started_at": started.isoformat(),
            "tickers_scanned": len(snaps),
            "alerts_generated": generated,
            "alerts_surfaced": surfaced,
            "macro_flag": macro_flag,
            "duration_ms": int((datetime.now() - started).total_seconds() * 1000),
            "errors": errs,
        }

    @property
    def stats(self) -> dict:
        return dict(self._stats)


class ScanScheduler:
    def __init__(
        self,
        *,
        data_provider: Callable[[], list[MarketSnapshot]],
        watchlist_provider: Callable[[], set[str]],
        macro_provider: Callable[[], dict],
        on_alert: Callable[[ScanAlert], None],
        data_root: Optional[Path] = None,
    ):
        self.data_provider = data_provider
        self.watchlist_provider = watchlist_provider
        self.macro_provider = macro_provider
        self.on_alert = on_alert
        self.data_root = data_root
        self.engine = ScanEngine()
        self._running = False
        self._t: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._t = threading.Thread(target=self._loop, daemon=True, name="ScanScheduler")
        self._t.start()

    def stop(self) -> None:
        self._running = False
        if self._t:
            self._t.join(timeout=10)

    def _loop(self) -> None:
        while self._running:
            try:
                if MarketHours.is_scan_active():
                    self._run_once()
                time.sleep(MarketHours.scan_interval_seconds())
            except Exception as e:
                logger.error("scanner loop error: %s", e)
                time.sleep(60)

    def _run_once(self) -> None:
        snaps = self.data_provider()
        wl = self._expand_watchlist(self.watchlist_provider())
        macro = self.macro_provider() or {}
        macro_flag = str(macro.get("macro_flag") or "NEUTRAL")
        run = self.engine.run(
            snaps=snaps,
            macro_flag=macro_flag,
            watchlist=wl,
            on_alert=self.on_alert,
            data_root=self.data_root,
        )
        logger.info("[scanner] scan: %s", run)

    def _expand_watchlist(self, wl: set[str]) -> set[str]:
        out = set(wl)
        for s in list(wl):
            out.update(RELATED_TICKERS.get(s, []))
        return out

    @property
    def stats(self) -> dict:
        return self.engine.stats


class ScannerAdapter:
    def __init__(self, *, store: ScannerStore):
        self.store = store
        self._alerts: list[ScanAlert] = []
        self._dismissed = store.load_dismissed()
        self._lock = threading.Lock()
        self._scheduler: Optional[ScanScheduler] = None

    def start(self, *, data_provider: Callable[[], list[MarketSnapshot]], watchlist_provider: Callable[[], set[str]], macro_provider: Callable[[], dict]) -> None:
        if self._scheduler is not None:
            return

        def on_alert(a: ScanAlert) -> None:
            if a.id in self._dismissed:
                return
            with self._lock:
                self._alerts.insert(0, a)
                self._alerts = self._alerts[:200]
            try:
                self.store.append_alert(a)
            except Exception:
                pass

        data_root = self.store.dir.parent
        self._scheduler = ScanScheduler(
            data_provider=data_provider,
            watchlist_provider=watchlist_provider,
            macro_provider=macro_provider,
            on_alert=on_alert,
            data_root=data_root,
        )
        self._scheduler.start()

    def stop(self) -> None:
        if self._scheduler:
            self._scheduler.stop()
            self._scheduler = None

    def get_alerts(self, *, limit: int = 50, ticker: Optional[str] = None, priority: Optional[ScanPriority] = None, include_dismissed: bool = False) -> list[dict]:
        with self._lock:
            arr = list(self._alerts)
        if not arr:
            rows = self.store.load_alerts(limit=limit)
            if not include_dismissed:
                rows = [r for r in rows if r.get("id") not in self._dismissed]
            if ticker:
                rows = [r for r in rows if r.get("ticker") == ticker.upper()]
            return rows[:limit]

        out: list[ScanAlert] = []
        for a in arr:
            if not include_dismissed and a.id in self._dismissed:
                continue
            if ticker and a.ticker != ticker.upper():
                continue
            if priority and a.priority != priority:
                continue
            out.append(a)
        return [a.to_dict() for a in out[:limit]]

    def dismiss(self, alert_id: str) -> None:
        self._dismissed.add(alert_id)
        self.store.save_dismissed(self._dismissed)

    @property
    def stats(self) -> dict:
        s = self._scheduler.stats if self._scheduler else self.store.read_stats()
        try:
            self.store.write_stats(s)
        except Exception:
            pass
        return s

