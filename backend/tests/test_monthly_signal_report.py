"""Monthly signal bucket aggregation (no EOD files required)."""
from __future__ import annotations

from signals.monthly_signal_report import aggregate_monthly_by_bucket
from signals.forward_tracking import signal_bucket_from_row


def test_signal_bucket_from_row():
    # HOLD/ADD requires entry_mode="full_go" — a high composite score alone is not an add
    # signal (avoids inflating HOLD/ADD forward stats with names that never actually cleared
    # gates). See signals/forward_tracking.py::signal_bucket_from_row.
    assert signal_bucket_from_row(
        {"composite_buy": 80, "entry_mode": "full_go"}, buy_min=70, sell_max=30
    ) == "HOLD/ADD"
    assert signal_bucket_from_row({"composite_buy": 80}, buy_min=70, sell_max=30) == "HOLD"
    assert signal_bucket_from_row({"composite_buy": 25}, buy_min=70, sell_max=30) == "CONSIDER TRIM"
    assert signal_bucket_from_row({"composite_buy": 50}, buy_min=70, sell_max=30) == "HOLD"


def test_aggregate_monthly_by_bucket():
    records = [
        {"as_of_date": "2026-01-05", "horizon_days": 5, "our_signal": "HOLD/ADD", "actual_return_pct": 1.0},
        {"as_of_date": "2026-01-06", "horizon_days": 5, "our_signal": "HOLD/ADD", "actual_return_pct": 3.0},
        {"as_of_date": "2026-01-05", "horizon_days": 20, "our_signal": "HOLD/ADD", "actual_return_pct": 2.0},
        {"as_of_date": "2026-02-01", "horizon_days": 5, "our_signal": "HOLD", "actual_return_pct": -0.5},
    ]
    out = aggregate_monthly_by_bucket(records, horizons=[5, 20])
    months = {m["month"]: m for m in out["months"]}
    assert "2026-01" in months
    assert "HOLD/ADD" in months["2026-01"]["buckets"]
    assert months["2026-01"]["buckets"]["HOLD/ADD"]["5"]["n"] == 2
    assert out["overall_by_bucket"]["HOLD/ADD"]["5"]["n"] == 2
