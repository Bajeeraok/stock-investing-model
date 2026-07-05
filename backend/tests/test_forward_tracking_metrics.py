"""Forward tracking path + TRIM metrics."""
from signals.forward_tracking_metrics import (
    aggregate_horizon_stats,
    compute_validated_forward_return,
    freeze_gate_fields_from_row,
    path_metrics,
    trim_outcome_metrics,
)


def test_path_metrics_target_before_stop():
    bars = [
        {"high": 105.0, "low": 99.0, "close": 104.0},
        {"high": 108.0, "low": 101.0, "close": 107.0},
    ]
    out = path_metrics(100.0, bars, stop=95.0, target=106.0)
    assert out["hit_st_target"] == 1
    assert out["hit_st_stop"] == 0


def test_trim_helped_when_stock_fell():
    t = trim_outcome_metrics(-4.5, "CONSIDER TRIM")
    assert t is not None
    assert t["trim_net_score_pct"] == 4.5
    assert t["trim_outcome_label"] == "helped_avoid_drawdown"


def test_aggregate_includes_trim():
    rows = [
        {"actual_return_pct": -3.0, "our_signal": "CONSIDER TRIM", "trim_net_score_pct": 3.0},
        {"actual_return_pct": 2.0, "hit_st_target": 0, "hit_st_stop": 0},
    ]
    s = aggregate_horizon_stats(rows)
    assert s["trim_n"] == 1
    assert s["trim_avg_net_score_pct"] == 3.0


def test_freeze_gate_fields():
    row = {
        "retail_status": {
            "gates": [
                {"id": "valuation", "label": "VAL", "pass": True, "detail": "ok"},
                {"id": "regime", "label": "REG", "pass": False, "detail": "no"},
                {"id": "momentum", "label": "MOM", "pass": True, "detail": "ok"},
                {"id": "ml", "label": "ML", "pass": True, "detail": "ok"},
            ],
            "gates_locked_count": 1,
            "go_no_go": "no_go",
        },
        "gate_cleared": False,
    }
    frozen = freeze_gate_fields_from_row(row)
    assert frozen["gates_frozen"] is True
    assert frozen["gates_passed"] == 3
    assert frozen["gates_total"] == 4


def test_stale_session_dropped():
    start = {"close": 100.0, "ohlcv_last_date": "2026-07-02"}
    end = {"close": 100.0, "ohlcv_last_date": "2026-07-02", "daily_move_pct": 0.0}
    ret, q = compute_validated_forward_return(start, end, horizon=1)
    assert ret is None
    assert q == "stale_session"


def test_crwd_style_reconcile_daily_move():
    """Broken close chain without ticker: daily_move fallback."""
    start = {"close": 512.0, "ohlcv_last_date": "2026-07-01", "high": 515, "low": 508}
    end = {
        "close": 128.0,
        "high": 130.0,
        "low": 126.0,
        "daily_move_pct": -1.2,
        "ohlcv_last_date": "2026-07-02",
    }
    ret, q = compute_validated_forward_return(start, end, horizon=1)
    assert ret == -1.2
    assert q == "reconciled_daily_move"


def test_crwd_4_for_1_split_adjusted():
    """CRWD Jul 2026 4-for-1: pre-split close aligned to post-split basis."""
    start = {"close": 760.0, "ohlcv_last_date": "2026-07-01", "high": 765, "low": 755}
    end = {
        "close": 196.80,
        "high": 198.0,
        "low": 194.0,
        "daily_move_pct": 1.87,
        "ohlcv_last_date": "2026-07-02",
    }
    ret, q = compute_validated_forward_return(start, end, horizon=1, ticker="CRWD")
    assert q == "split_adjusted"
    assert ret is not None
    assert -5.0 < ret < 8.0
    assert ret > -10.0  # not the bogus -74% raw close chain


def test_outlier_dropped_when_no_reconcile():
    start = {"close": 500.0, "ohlcv_last_date": "2026-07-01"}
    end = {"close": 125.0, "high": 128.0, "low": 124.0, "ohlcv_last_date": "2026-07-02"}
    ret, q = compute_validated_forward_return(start, end, horizon=1)
    assert ret is None
    assert q == "outlier_abs_cap"
