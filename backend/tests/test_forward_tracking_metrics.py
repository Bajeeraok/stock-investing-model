"""Forward tracking path + TRIM metrics."""
from signals.forward_tracking_metrics import (
    path_metrics,
    trim_outcome_metrics,
    aggregate_horizon_stats,
    freeze_gate_fields_from_row,
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
