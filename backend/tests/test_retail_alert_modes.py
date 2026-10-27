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
    state = {"AAA": {"last_price": 96.0}, "BBB": {"last_price": 96.0}}
    alerts, _ = evaluate_retail_alerts(snaps, levels, state, {}, {"AAA", "BBB"}, portfolio={"AAA"})
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


def _stop_alerts(levels, prev_price, price):
    state = {"AAA": {"last_price": prev_price}} if prev_price is not None else {}
    alerts, new_state = evaluate_retail_alerts([_snap("AAA", price)], {"AAA": levels}, state, {}, {"AAA"}, portfolio={"AAA"})
    return [a for a in alerts if a.type in (AlertType.STOP_HIT, AlertType.STOP_APPROACHING)], new_state


def test_stop_fires_once_on_cross_not_while_below():
    fired, st = _stop_alerts(LEVELS, 96.0, 85.0)
    assert [a.type for a in fired] == [AlertType.STOP_HIT]
    again, _ = _stop_alerts(LEVELS, st["AAA"]["last_price"], 84.0)
    assert again == []
    first_scan, _ = _stop_alerts(LEVELS, None, 85.0)
    assert first_scan == []


def test_no_stop_alerts_for_long_term_band():
    long_levels = {"long": {**LEVELS["short"], "stop_loss": 310.0, "entry_low": 320.0, "entry_high": 340.0, "horizon_label": "Long-term"}}
    fired, _ = _stop_alerts(long_levels, 330.0, 253.0)
    assert fired == []


def _target_alerts(levels, prev_price, price):
    state = {"AAA": {"last_price": prev_price}} if prev_price is not None else {}
    alerts, new_state = evaluate_retail_alerts([_snap("AAA", price)], {"AAA": levels}, state, {}, {"AAA"}, portfolio={"AAA"})
    return [a for a in alerts if a.type in (AlertType.TARGET_HIT, AlertType.TARGET_APPROACHING)], new_state


def test_target_fires_once_on_cross_not_while_above():
    fired, st = _target_alerts(LEVELS, 110.0, 121.0)
    assert [a.type for a in fired] == [AlertType.TARGET_HIT]
    assert "HOLD" in fired[0].actionable
    again, _ = _target_alerts(LEVELS, st["AAA"]["last_price"], 122.0)
    assert again == []
    near, _ = _target_alerts(LEVELS, 110.0, 115.0)
    assert [a.type for a in near] == [AlertType.TARGET_APPROACHING]
    still_near, _ = _target_alerts(LEVELS, 115.0, 116.0)
    assert still_near == []


def test_no_target_alerts_for_long_term_band():
    long_levels = {"long": {**LEVELS["short"], "horizon_label": "Long-term"}}
    fired, _ = _target_alerts(long_levels, 110.0, 121.0)
    assert fired == []


def test_readiness_cache_follows_retail_action(tmp_path):
    from scanner.horizon_levels import read_readiness_cache, sync_horizon_levels_from_signal_results

    row = {
        "ticker": "XLK", "close": 180.0, "gates_passed": 4, "gates_total": 4, "go_no_go": "go",
        "investor_summary": {
            "retail_action": {"go_no_go": "no_go", "entry_mode": "hard_lock"},
            "actionable_score": {"factors": {"gates_passed": 3, "gates_total": 4}},
        },
    }
    sync_horizon_levels_from_signal_results(tmp_path, [row])
    rd = read_readiness_cache(tmp_path)["XLK"]
    assert rd["go_no_go"] == "no_go" and rd["entry_mode"] == "hard_lock"
    assert rd["gates_passed"] == 3 and rd["go_ready"] is False
