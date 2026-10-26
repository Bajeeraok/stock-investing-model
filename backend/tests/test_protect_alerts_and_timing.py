from scanner.dashboard_alerts import evaluate_protect_mode_alerts
from scanner.ticker_universe import AlertType
from signals.forward_tracking_metrics import aggregate_timing_vs_hold


def _rows(aapl_close, spy_close=500.0):
    return {
        "AAPL": {"ticker": "AAPL", "close": aapl_close, "ma200": 100.0},
        "SPY": {"ticker": "SPY", "close": spy_close, "ma200": 450.0},
    }


def test_protect_alert_fires_only_on_flip(tmp_path):
    assert evaluate_protect_mode_alerts(_rows(120.0), {"AAPL"}, tmp_path) == []
    assert evaluate_protect_mode_alerts(_rows(119.0), {"AAPL"}, tmp_path) == []
    on = evaluate_protect_mode_alerts(_rows(90.0), {"AAPL"}, tmp_path)
    assert len(on) == 1 and on[0].type == AlertType.PROTECT_MODE_ON
    assert "not a sell signal" in on[0].body
    assert evaluate_protect_mode_alerts(_rows(99.5), {"AAPL"}, tmp_path) == []  # inside hysteresis band
    off = evaluate_protect_mode_alerts(_rows(110.0), {"AAPL"}, tmp_path)
    assert len(off) == 1 and off[0].type == AlertType.PROTECT_MODE_OFF


def test_protect_alert_on_spy_risk_off(tmp_path):
    evaluate_protect_mode_alerts(_rows(120.0), {"AAPL"}, tmp_path)
    on = evaluate_protect_mode_alerts(_rows(120.0, spy_close=400.0), {"AAPL"}, tmp_path)
    assert len(on) == 1 and on[0].signals["spy_risk_off"] is True


def _rec(tk, sig, ret, exc=None):
    return {"ticker": tk, "our_signal": sig, "horizon_days": 20, "actual_return_pct": ret,
            "excess_return_pct": exc, "data_quality": "ok", "forward_status": "complete"}


def test_timing_vs_hold_edge():
    rows = [_rec("A", "HOLD", 2.0), _rec("A", "HOLD", 2.0), _rec("A", "ADD", 6.0, 1.0), _rec("B", "WATCH", -1.0)]
    out = aggregate_timing_vs_hold(rows)
    by = out["by_signal"]
    assert by["ADD"]["hold_same_stock_avg_return_pct"] == round(10 / 3, 2)
    assert by["ADD"]["edge_vs_hold_pct"] == round(6 - 10 / 3, 2)
    assert by["WATCH"]["edge_vs_hold_pct"] == 0.0
    assert by["ADD"]["avg_excess_vs_spy_pct"] == 1.0
