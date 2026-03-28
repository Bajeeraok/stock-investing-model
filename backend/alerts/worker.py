from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from alerts.engine import OptionsAlertsEngine
from alerts.events import AlertEvent, AlertEventStore
from alerts.market_hours import is_us_market_hours, seconds_until_next_scan

logger = logging.getLogger("alerts.worker")


def _options_iv_worker_enabled() -> bool:
    """Tradier IV snapshots + IV_EXTREME feed; off by default (use band alerts in scanner instead)."""
    try:
        from config_loader import load_config

        return bool((load_config().get("alerts") or {}).get("enable_options_iv_worker", False))
    except Exception:
        return False


def _load_symbols() -> list[str]:
    """
    Default symbol universe: config watchlist + portfolio tickers (deduped).
    """
    try:
        from config_loader import load_config
        cfg = load_config()
        wl = cfg.get("watchlist") or []
        portfolios = cfg.get("portfolios") or {}
        holdings = []
        if isinstance(portfolios, dict):
            for v in portfolios.values():
                if isinstance(v, list):
                    for h in v:
                        if isinstance(h, dict) and h.get("ticker"):
                            holdings.append(h["ticker"])
                        elif isinstance(h, str):
                            holdings.append(h)
        symbols = [*wl, *holdings]
    except Exception:
        symbols = []
    # Env override: ALERTS_SYMBOLS="NVDA,SPY,QQQ"
    env = os.getenv("ALERTS_SYMBOLS")
    if env:
        symbols = [s.strip().upper() for s in env.split(",") if s.strip()]
    # Cap
    max_n = int(os.getenv("ALERTS_MAX_SYMBOLS", "25"))
    out: list[str] = []
    for s in symbols:
        sym = str(s).upper().strip()
        if sym and sym not in out:
            out.append(sym)
    return out[:max_n]


def _macro_flag(vix: float | None, es_change: float | None) -> tuple[str, int]:
    v = float(vix or 18.0)
    es = float(es_change or 0.0)
    risk = 0
    if v > 25:
        risk += 3
    elif v > 22:
        risk += 2
    elif v > 20:
        risk += 1
    if es < -1.0:
        risk += 3
    elif es < -0.5:
        risk += 2
    elif es < -0.2:
        risk += 1
    elif es > 0.5:
        risk -= 1
    flag = "RISK_OFF" if risk >= 4 else "RISK_ON" if risk <= -1 else "NEUTRAL"
    return flag, int(risk)


def run_worker(data_root: Path) -> None:
    scan_interval_sec = int(os.getenv("ALERTS_SCAN_INTERVAL_SEC", "300"))  # 5 min
    weekdays_only = os.getenv("ALERTS_WEEKDAYS_ONLY", "true").lower() == "true"
    market_hours_only = os.getenv("ALERTS_MARKET_HOURS_ONLY", "true").lower() == "true"

    engine = OptionsAlertsEngine(data_root=data_root)
    store = AlertEventStore(data_root=data_root)

    symbols = _load_symbols()
    logger.info("[alerts] worker start: symbols=%d scan_interval=%ss", len(symbols), scan_interval_sec)

    # Daily IV snapshot refresh (8:00 ET) — naive check once per loop
    last_daily_refresh_key = None

    while True:
        try:
            if not _options_iv_worker_enabled():
                logger.info("[alerts] options IV worker disabled (alerts.enable_options_iv_worker=false); sleeping 1h")
                time.sleep(3600)
                continue

            # Sleep until next scan window when outside market hours
            sleep_for = seconds_until_next_scan(
                scan_interval_seconds=scan_interval_sec,
                weekdays_only=weekdays_only,
                market_hours_only=market_hours_only,
            )
            if not is_us_market_hours() and market_hours_only:
                logger.info("[alerts] outside market hours — sleeping %ss", sleep_for)
                time.sleep(sleep_for)
                continue

            start = time.time()

            # Daily refresh gate at ~08:00 ET
            try:
                from alerts.market_hours import ET
                now_et = datetime.now(tz=ET)
                daily_key = now_et.strftime("%Y-%m-%d")
                if now_et.hour == 8 and last_daily_refresh_key != daily_key:
                    logger.info("[alerts] daily IV snapshot refresh…")
                    r = engine.refresh_daily_iv_snapshots(symbols)
                    logger.info("[alerts] IV refresh updated=%s skipped=%s errors=%d", r.get("updated"), r.get("skipped"), len(r.get("errors") or {}))
                    last_daily_refresh_key = daily_key
            except Exception as e:
                logger.warning("[alerts] daily refresh failed: %s", e)

            latest = engine.scan_watchlist(symbols)

            # Macro: reuse existing Thrive Alpha macro pieces (VIX, ES) if available later.
            # For now, infer macro flag from (optional) values inside latest when added.
            macro = {"vix": None, "es_futures_change": None}
            flag, risk = _macro_flag(macro.get("vix"), macro.get("es_futures_change"))
            macro["macro_flag"] = flag
            macro["risk_score"] = risk

            store.write_latest({"macro": macro, **latest})

            # Event generation (minimal v1): macro flag transitions + IV extreme candidates
            events: list[AlertEvent] = []
            for s in latest.get("signals") or []:
                ivr = s.get("iv_rank")
                if ivr is not None and ivr >= 80:
                    events.append(
                        AlertEvent.create(
                            ticker=s.get("ticker") or "",
                            alert_type="IV_EXTREME",
                            severity="HIGH",
                            title="IV extreme",
                            message=f"IV Rank {ivr} (extreme) — premium rich; covered calls/spreads attractive.",
                            payload=s,
                            dedupe_key=f"{s.get('ticker')}:IV_EXTREME:{datetime.now(tz=timezone.utc).strftime('%Y-%m-%d')}",
                        )
                    )

            store.append_events(events)

            elapsed_ms = int((time.time() - start) * 1000)
            status = {
                "as_of": datetime.now(tz=timezone.utc).isoformat(),
                "symbols_scanned": len(symbols),
                "events_written": len(events),
                "elapsed_ms": elapsed_ms,
                "scan_interval_sec": scan_interval_sec,
                "market_hours_only": market_hours_only,
                "weekdays_only": weekdays_only,
            }
            store.write_status(status)

            # Sleep to next interval boundary
            sleep_for = seconds_until_next_scan(
                scan_interval_seconds=scan_interval_sec,
                weekdays_only=weekdays_only,
                market_hours_only=market_hours_only,
            )
            time.sleep(sleep_for)

        except KeyboardInterrupt:
            logger.info("[alerts] worker stopped")
            return
        except Exception as e:
            logger.exception("[alerts] worker loop error: %s", e)
            time.sleep(10)


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    run_worker(data_root=root / "data")


if __name__ == "__main__":
    main()

