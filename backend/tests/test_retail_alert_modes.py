from scanner.engine import MarketSnapshot, evaluate_retail_alerts
from scanner.ticker_universe import AlertType, ScanTier


def _snap(sym, price):
    return MarketSnapshot(
        symbol=sym, price=price, price_change_pct=0.0, regime="UP", regime_confidence=60.0,
        iv_rank=0.0, iv_percentile=0.0, call_put_flow_ratio=1.0, er_days_away=None, vix=15.0,
        atr_pct=2.0, support_level=None, kelly_base=0.0, in_watchlist=True,
        scan_tier=ScanTier.TIER1_CORE, sector="Tech",
    )


LEVELS = {"short": {"entry_low": 95.0, "entry_high": 100.0, "stop_loss": 90.0, "target": 120.0, "horizon_label": "Short-term"}}


def test_stop_and_target_alerts_only_for_holdings():
    levels = {"AAA": LEVELS, "BBB": LEVELS}
    snaps = [_snap("AAA", 85.0), _snap("BBB", 85.0)]
    alerts, _ = evaluate_retail_alerts(snaps, levels, {}, {}, {"AAA", "BBB"}, portfolio={"AAA"})
    stop = [a for a in alerts if a.type == AlertType.STOP_HIT]
    assert [a.ticker for a in stop] == ["AAA"]
    assert "HOLD" in stop[0].actionable
    assert stop[0].signals["held"] is True and "entryMode" in stop[0].signals


def test_rsi_alert_is_informational():
    s = _snap("AAA", 110.0)
    s.rsi = 30.0
    alerts, _ = evaluate_retail_alerts([s], {}, {}, {}, {"AAA"}, portfolio={"AAA"})
    rsi = [a for a in alerts if a.type == AlertType.RSI_OVERSOLD]
    assert rsi and "not" in rsi[0].actionable.lower()
