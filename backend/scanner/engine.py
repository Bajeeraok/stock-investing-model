from __future__ import annotations

import hashlib
import logging
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import Callable, Optional

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
}


def _alert_id(ticker: Optional[str], alert_type: AlertType) -> str:
    raw = f"{ticker or 'MACRO'}:{alert_type}:{datetime.now().strftime('%Y%m%d%H%M')}"
    return hashlib.md5(raw.encode()).hexdigest()[:12]


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
            },
            scan_tier=snap.scan_tier,
            surface_to_all=SURFACING_THRESHOLDS[alert_type].surface_to_all,
        )


class AlertDeduplicator:
    def __init__(self):
        self._last: dict[tuple[str, AlertType], datetime] = {}
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
        }

    def is_dup(self, ticker: str, t: AlertType) -> bool:
        key = (ticker, t)
        last = self._last.get(key)
        if not last:
            return False
        cd = self.cooldowns_min.get(t, 60)
        return (datetime.now() - last).total_seconds() < cd * 60

    def record(self, ticker: str, t: AlertType) -> None:
        self._last[(ticker, t)] = datetime.now()

    def prune(self) -> None:
        cutoff = datetime.now() - timedelta(hours=12)
        self._last = {k: v for k, v in self._last.items() if v >= cutoff}


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
            return 60 * 5
        return 60 * 30


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

    def run(self, *, snaps: list[MarketSnapshot], macro_flag: str, watchlist: set[str], on_alert: Callable[[ScanAlert], None]) -> dict:
        started = datetime.now()
        generated = 0
        surfaced = 0
        errs: list[str] = []
        for s in snaps:
            try:
                alerts = self.eval.evaluate(s, macro_flag, watchlist)
                generated += len(alerts)
                for a in alerts:
                    if self.dedupe.is_dup(a.ticker or "?", a.type):
                        continue
                    self.dedupe.record(a.ticker or "?", a.type)
                    on_alert(a)
                    surfaced += 1
            except Exception as e:
                errs.append(f"{s.symbol}: {e}")
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
    ):
        self.data_provider = data_provider
        self.watchlist_provider = watchlist_provider
        self.macro_provider = macro_provider
        self.on_alert = on_alert
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
        run = self.engine.run(snaps=snaps, macro_flag=macro_flag, watchlist=wl, on_alert=self.on_alert)
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

        self._scheduler = ScanScheduler(
            data_provider=data_provider,
            watchlist_provider=watchlist_provider,
            macro_provider=macro_provider,
            on_alert=on_alert,
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

