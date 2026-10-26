"""
Retail alerts chained to dashboard Refresh — same bands/gates as signals, one 15m pipeline.

- Action book (get_dashboard_signal_universe): fresh signal rows + synced horizon_levels.
- Audit cohort (100): price-only snapshots + cached bands from last EOD/sync (no full recompute).
- Cohort tickers without bands get ATR-based bands written so ENTRY_ZONE alerts can fire.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from scanner.engine import MarketSnapshot, ScanEngine
from scanner.horizon_levels import read_horizon_levels, write_horizon_levels
from scanner.store import ScannerStore
from scanner.ticker_universe import AlertType, ScanTier, TICKER_META

logger = logging.getLogger("scanner.dashboard_alerts")


def _alert_settings(config: dict) -> dict[str, Any]:
    a = (config or {}).get("alerts") or {}
    return {
        "enabled": a.get("evaluate_on_dashboard_refresh", True) is not False,
        "include_audit_cohort": a.get("include_audit_cohort_on_refresh", True) is not False,
    }


def _watchlist_set(config: dict) -> tuple[set[str], set[str]]:
    """Return (full_watchlist, portfolio_only).
    full_watchlist includes portfolio + explicit watchlist tickers.
    portfolio_only is just the holdings — used for verbosity split.
    """
    from config_loader import portfolio_tickers_from_config

    portfolio = {str(t).upper() for t in portfolio_tickers_from_config(config)}
    wl = {str(t).upper() for t in (config.get("watchlist") or []) if t}
    wl.update(portfolio)
    return wl, portfolio


def _macro_flag_from_results(results: list[dict]) -> str:
    for r in results or []:
        if not isinstance(r, dict):
            continue
        if str(r.get("ticker") or "").upper() == "SPY":
            g = r.get("_global_market_regime")
            if g:
                gsu = str(g).upper()
                if "BEAR" in gsu or gsu == "DOWN":
                    return "RISK_OFF"
                if "BULL" in gsu or gsu == "UP":
                    return "RISK_ON"
    return "NEUTRAL"


def snapshot_from_signal_row(row: dict, *, watchlist: set[str], vix: float = 18.0) -> MarketSnapshot | None:
    """Build scanner snapshot from a dashboard signal row (fresh bands/gates on this ticker)."""
    ticker = str(row.get("ticker") or "").upper().strip()
    if not ticker or row.get("error"):
        return None
    try:
        price = float(row.get("close") or 0)
    except (TypeError, ValueError):
        return None
    if price <= 0:
        return None
    meta = TICKER_META.get(ticker)
    try:
        chg = float(row.get("change_pct") or row.get("price_change_pct") or 0)
    except (TypeError, ValueError):
        chg = 0.0
    regime = str(row.get("regime") or "NEUTRAL").upper()
    try:
        score = float(row.get("composite_buy") or 50)
    except (TypeError, ValueError):
        score = 50.0
    er = row.get("earnings_days_until")
    try:
        er_days = int(er) if er is not None else None
    except (TypeError, ValueError):
        er_days = None
    atr_pct = 2.5
    try:
        atr = row.get("atr14") or row.get("atr_pct")
        if atr is not None and float(row.get("close") or price) > 0:
            atr_pct = float(atr) / float(price) * 100.0 if float(atr) < 50 else float(atr)
    except (TypeError, ValueError):
        pass
    ml = row.get("ml_short_prob")
    ml_short = None
    if ml is not None:
        try:
            pv = float(ml)
            ml_short = pv * 100.0 if pv <= 1.0 else pv
        except (TypeError, ValueError):
            pass
    rsi_raw = row.get("rsi") or row.get("rsi14")
    rsi_val: float | None = None
    if rsi_raw is not None:
        try:
            rsi_val = float(rsi_raw)
        except (TypeError, ValueError):
            pass
    return MarketSnapshot(
        symbol=ticker,
        price=price,
        price_change_pct=chg,
        regime=regime,
        regime_confidence=score,
        iv_rank=50.0,
        iv_percentile=50.0,
        call_put_flow_ratio=1.0,
        er_days_away=er_days,
        vix=float(vix),
        atr_pct=max(0.5, float(atr_pct)),
        support_level=round(price * 0.95, 2),
        kelly_base=0.05,
        in_watchlist=ticker in watchlist,
        scan_tier=meta.tier if meta else ScanTier.TIER1_CORE,
        sector=meta.sector if meta else "Unknown",
        ml_prob_short=ml_short,
        rsi=rsi_val,
    )


def snapshot_from_price_only(
    ticker: str,
    price: float,
    *,
    watchlist: set[str],
    vix: float = 18.0,
    regime: str = "NEUTRAL",
    regime_confidence: float = 50.0,
) -> MarketSnapshot | None:
    """Cohort-only path: cached bands in horizon_levels, live price for cross checks."""
    ticker = ticker.upper().strip()
    if not ticker or price <= 0:
        return None
    meta = TICKER_META.get(ticker)
    return MarketSnapshot(
        symbol=ticker,
        price=float(price),
        price_change_pct=0.0,
        regime=regime,
        regime_confidence=regime_confidence,
        iv_rank=50.0,
        iv_percentile=50.0,
        call_put_flow_ratio=1.0,
        er_days_away=None,
        vix=float(vix),
        atr_pct=2.5,
        support_level=round(price * 0.95, 2),
        kelly_base=0.05,
        in_watchlist=ticker in watchlist,
        scan_tier=meta.tier if meta else ScanTier.TIER1_CORE,
        sector=meta.sector if meta else "Unknown",
        ml_prob_short=None,
    )


def _write_atr_bands_for_cohort(
    tickers: list[str],
    price_map: dict[str, float],
    levels: dict[str, dict],
    data_root: Path,
    *,
    atr_pct_default: float = 2.5,
) -> int:
    """
    Write ATR-based ST bands into horizon_levels.json for cohort tickers that have
    no cached bands (never opened in modal, never in signal universe).

    Band method:
      entry_low  = price * (1 - 0.5 * atr_pct)     — within half an ATR of spot
      entry_high = price * (1 - 0.15 * atr_pct)    — just below spot (tight buy zone)
      stop_loss  = price * (1 - 1.5 * atr_pct)     — 1.5× ATR below spot
      target     = price * (1 + 2.0 * atr_pct)     — 2× ATR above spot (risk:reward ~2:1)

    Only writes for tickers with a known price and no existing bands. Existing
    modal-derived or signal-derived bands are never overwritten.
    Returns count of tickers written.
    """
    updated = dict(levels)
    written = 0
    for t in tickers:
        if t in updated and updated[t]:
            continue  # already has bands — don't overwrite
        p = price_map.get(t)
        if not p or p <= 0:
            continue
        atr_frac = atr_pct_default / 100.0
        el = round(p * (1 - 0.50 * atr_frac * 100 / 100), 2)
        eh = round(p * (1 - 0.15 * atr_frac * 100 / 100), 2)
        sl = round(p * (1 - 1.50 * atr_frac * 100 / 100), 2)
        tgt = round(p * (1 + 2.00 * atr_frac * 100 / 100), 2)
        if el >= eh or sl >= el:
            continue
        updated[t] = {
            "short": {
                "entry_low": el,
                "entry_high": eh,
                "stop_loss": sl,
                "target": tgt,
                "horizon_label": "Short-term (ATR proxy)",
                "band_source": "atr_cohort",
            }
        }
        written += 1
    if written:
        write_horizon_levels(data_root, updated)
        levels.update(updated)
    return written


def _cohort_only_with_bands(
    audit_tickers: set[str],
    dashboard_tickers: set[str],
    levels: dict[str, dict],
) -> list[str]:
    out: list[str] = []
    for t in sorted(audit_tickers):
        if t in dashboard_tickers:
            continue
        if t not in levels or not levels[t]:
            continue
        out.append(t)
    return out


def _fetch_prices_for_tickers(tickers: list[str], config: dict, existing: dict[str, float] | None) -> dict[str, float]:
    prices = dict(existing or {})
    missing = [t for t in tickers if t not in prices or not prices.get(t)]
    if not missing:
        return prices
    try:
        from signals.fmp_client import fetch_batch_quote, get_api_key as get_fmp_api_key

        if get_fmp_api_key(config):
            batch, err = fetch_batch_quote(config, missing)
            if batch and not err:
                for sym, row in batch.items():
                    p = row.get("price")
                    if p is not None:
                        try:
                            prices[str(sym).upper()] = float(p)
                        except (TypeError, ValueError):
                            pass
                return prices
    except Exception as e:
        logger.debug("cohort alert batch quote: %s", e)
    try:
        from signals.fetcher import fetch_yfinance_latest_prices

        yf = fetch_yfinance_latest_prices(missing)
        for k, v in (yf or {}).items():
            prices[str(k).upper()] = float(v)
    except Exception as e:
        logger.debug("cohort alert yfinance: %s", e)
    return prices



def _ma200_state(row: dict | None, prev: bool | None, band_pct: float = 1.0) -> bool | None:
    """True when close is below MA200 (1% hysteresis band, same rule as signals.protect_mode)."""
    if not row:
        return None
    try:
        close, ma = float(row.get("close") or 0), float(row.get("ma200") or 0)
    except (TypeError, ValueError):
        return None
    if close <= 0 or ma <= 0:
        return None
    if close < ma * (1 - band_pct / 100.0):
        return True
    if close > ma * (1 + band_pct / 100.0):
        return False
    return bool(prev) if prev is not None else close < ma


def evaluate_protect_mode_alerts(
    rows_by_ticker: dict[str, dict],
    tickers: set[str],
    data_root: Path,
    *,
    reduced_pct: int = 50,
) -> list:
    """PROTECT_MODE_ON/OFF when a held/watched stock's optional protect state flips.

    Protect = stock below its own 200-day average or SPY below its 200-day average. On flip only
    (state persisted in alerts/protect_state.json); first observation just records state.
    """
    from scanner.engine import _build_retail_alert
    from signals.time_et import today_est

    path = Path(data_root) / "alerts" / "protect_state.json"
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        state = {}
    spy_prev = (state.get("SPY") or {}).get("below")
    spy_below = _ma200_state(rows_by_ticker.get("SPY"), spy_prev)
    if spy_below is not None:
        state["SPY"] = {"below": spy_below}
    alerts = []
    today = today_est()
    for t in sorted(tickers):
        row = rows_by_ticker.get(t)
        if not row or t == "SPY":
            continue
        st = state.get(t) or {}
        below = _ma200_state(row, st.get("below"))
        if below is None:
            continue
        active = bool(below or spy_below)
        prev_active = st.get("active")
        state[t] = {"below": below, "active": active}
        if prev_active is None or prev_active == active:
            continue
        reasons = []
        if below:
            reasons.append("below its 200-day average")
        if spy_below:
            reasons.append("SPY is risk-off (below its 200-day average)")
        if active:
            atype = AlertType.PROTECT_MODE_ON
            head = f"{t} protect mode on (optional): ~{reduced_pct}% position"
            body = (
                f"{t}: {' and '.join(reasons)}. If you use protect mode, hold about {reduced_pct}% of a full "
                "position. Default is still HOLD — this is drawdown insurance, not a sell signal."
            )
        else:
            atype = AlertType.PROTECT_MODE_OFF
            head = f"{t} protect mode off: full position"
            body = f"{t} is back above its 200-day average and SPY is not risk-off. Protect mode returns to a full position."
        alerts.append(
            _build_retail_alert(
                t, atype, head, body, ScanTier.TIER1_CORE,
                {"price": row.get("close"), "ma200": row.get("ma200"), "stock_below_ma200": below,
                 "spy_risk_off": spy_below, "suggested_position_pct": reduced_pct if active else 100},
                one_liner=head,
                dedupe_extra=today,
            )
        )
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state), encoding="utf-8")
    except Exception as e:
        logger.debug("protect_state save failed: %s", e)
    return alerts


def run_retail_alerts_from_dashboard_refresh(
    results: list[dict],
    config: dict,
    data_root: Path,
    *,
    prices_by_ticker: dict[str, float] | None = None,
    vix: float | None = None,
) -> dict[str, Any]:
    """
    Evaluate retail alerts after horizon_levels sync on dashboard Refresh.
    Returns summary for logs / optional API payload.
    """
    settings = _alert_settings(config)
    if not settings["enabled"]:
        return {"skipped": True, "reason": "evaluate_on_dashboard_refresh disabled"}

    from config_loader import get_audit_cohort_tickers, get_dashboard_signal_universe

    data_root = Path(data_root)
    watchlist, portfolio_tickers = _watchlist_set(config)
    dashboard_universe = {str(t).upper() for t in get_dashboard_signal_universe(config)}
    audit_universe: set[str] = set()
    if settings["include_audit_cohort"]:
        audit_universe = {str(t).upper() for t in get_audit_cohort_tickers(config)}

    rows_by_ticker: dict[str, dict] = {}
    for r in results or []:
        if isinstance(r, dict) and r.get("ticker") and not r.get("error"):
            rows_by_ticker[str(r["ticker"]).upper()] = r

    vix_level = float(vix) if vix is not None else 18.0
    for item in results or []:
        if isinstance(item, dict) and str(item.get("ticker") or "").upper() in ("VIX", "^VIX"):
            # not used for vix level from row typically
            pass
    macro_flag = _macro_flag_from_results(results)

    snaps: list[MarketSnapshot] = []
    for t in sorted(dashboard_universe):
        row = rows_by_ticker.get(t)
        if row:
            snap = snapshot_from_signal_row(row, watchlist=watchlist, vix=vix_level)
            if snap:
                snaps.append(snap)

    levels = read_horizon_levels(data_root)

    # Pre-fetch prices for the full audit cohort so ATR band writing and alert
    # evaluation both share the same price call.
    all_cohort = [t for t in sorted(audit_universe) if t not in dashboard_universe]
    price_map = _fetch_prices_for_tickers(
        all_cohort,
        config,
        {str(k).upper(): float(v) for k, v in (prices_by_ticker or {}).items()},
    )

    # Write ATR-based bands for cohort tickers that have never had bands written.
    # This ensures ENTRY_ZONE_ENTERED can fire for the full cohort, not just modal-visited tickers.
    bands_written = _write_atr_bands_for_cohort(all_cohort, price_map, levels, data_root)
    if bands_written:
        logger.info("[dashboard] cohort ATR bands written for %d new tickers", bands_written)

    cohort_only = _cohort_only_with_bands(audit_universe, dashboard_universe, levels)
    spy_row = rows_by_ticker.get("SPY")
    cohort_regime = str((spy_row or {}).get("regime") or "NEUTRAL")
    cohort_conf = float((spy_row or {}).get("composite_buy") or 50) if spy_row else 50.0
    for t in cohort_only:
        p = price_map.get(t)
        if p is None or p <= 0:
            continue
        snap = snapshot_from_price_only(
            t,
            p,
            watchlist=watchlist,
            vix=vix_level,
            regime=cohort_regime,
            regime_confidence=cohort_conf,
        )
        if snap:
            snaps.append(snap)

    if not snaps:
        return {"skipped": True, "reason": "no snapshots", "dashboard_tickers": len(dashboard_universe)}

    store = ScannerStore(data_root)
    appended = 0

    try:
        protect_alerts = evaluate_protect_mode_alerts(rows_by_ticker, watchlist | set(portfolio_tickers), data_root)
    except Exception as e:
        logger.debug("protect-mode alerts failed: %s", e)
        protect_alerts = []
    try:
        protect_state = json.loads((Path(data_root) / "alerts" / "protect_state.json").read_text(encoding="utf-8"))
    except Exception:
        protect_state = {}
    held = {str(t).upper() for t in portfolio_tickers}

    def on_alert(a) -> None:
        nonlocal appended
        if a.id in store.load_dismissed():
            return
        t = str(a.ticker or "").upper()
        ps = protect_state.get(t) or {}
        if "active" in ps:
            a.signals = {**(a.signals or {}), "protectActive": bool(ps["active"])}
        if t and "held" not in (a.signals or {}):
            a.signals = {**(a.signals or {}), "held": t in held}
        store.append_alert(a)
        appended += 1

    engine = ScanEngine()
    run = engine.run(
        snaps=snaps,
        macro_flag=macro_flag,
        watchlist=watchlist,
        portfolio=portfolio_tickers,
        on_alert=on_alert,
        data_root=data_root,
        enable_options_alerts=False,
    )

    for a in protect_alerts:
        on_alert(a)

    from signals.time_et import now_iso_et

    now = now_iso_et()
    store.write_stats(
        {
            "as_of": now,
            "source": "dashboard_refresh",
            "universe_size": len(snaps),
            "dashboard_tickers": len(dashboard_universe),
            "cohort_price_only": len(cohort_only),
            "alerts_appended": appended,
            "last_scan_at": run.get("started_at") or now,
        }
    )

    summary = {
        "skipped": False,
        "as_of": now,
        "snapshots": len(snaps),
        "dashboard_tickers": len(dashboard_universe),
        "cohort_price_only_evaluated": sum(1 for s in snaps if s.symbol in cohort_only),
        "alerts_appended": appended,
        "alerts_generated": run.get("alerts_generated"),
        "alerts_surfaced": run.get("alerts_surfaced"),
    }
    logger.info("[dashboard] retail alerts after refresh: %s", summary)
    return summary
