"""Per-ticker forward-tracking index: built from ALL records (not the capped list), daily calls newest-first."""
from signals.forward_tracking import _build_by_ticker_index, _call_right


def _rec(tk, d, h, sig, ret):
    return {
        "ticker": tk, "as_of_date": d, "next_date": d, "horizon_days": h, "our_signal": sig,
        "actual_return_pct": ret, "forward_status": "complete", "model_version": "v1",
        "close_at_signal": 100.0, "close_at_forward": 100.0 + (ret or 0),
    }


def test_call_right_by_direction():
    assert _call_right("HOLD/ADD", 1.2) is True
    assert _call_right("HOLD/ADD", -0.5) is False
    assert _call_right("CONSIDER TRIM", -0.5) is True
    assert _call_right("HOLD", 2.0) is None
    assert _call_right("HOLD/ADD", None) is None


def test_by_ticker_daily_calls_newest_first_and_per_ticker():
    recs = [_rec("REGN", f"2026-10-{d:02d}", 1, "HOLD/ADD", 0.5) for d in range(1, 16)]
    recs += [_rec("REGN", "2026-10-01", 5, "HOLD/ADD", 2.0), _rec("MSFT", "2026-10-14", 1, "CONSIDER TRIM", -1.0)]
    idx = _build_by_ticker_index(recs)
    assert set(idx) == {"REGN", "MSFT"}
    calls = idx["REGN"]["daily_calls"]
    assert calls[0]["date"] == "2026-10-15" and len(calls) == 15
    assert all(c["right"] is True for c in calls)
    assert idx["REGN"]["latest_call_date"] == "2026-10-15"
    assert idx["MSFT"]["daily_calls"][0]["right"] is True


def test_latest_open_call_leads_daily_calls():
    from signals.forward_tracking import _build_by_ticker_index, _latest_open_calls

    rows = {"2026-11-09": {"NVDA": {"ticker": "NVDA", "signal": "HOLD", "close": 178.67, "gates_frozen": True}}}
    op = _latest_open_calls(["2026-11-06", "2026-11-09"], rows, buy_min=70, sell_max=30)
    rec = {"ticker": "NVDA", "horizon_days": 1, "as_of_date": "2026-11-06", "next_date": "2026-11-09",
           "our_signal": "HOLD", "forward_status": "complete", "actual_return_pct": -4.27, "model_version": "2026.11.3"}
    tr = _build_by_ticker_index([rec], None, op)["NVDA"]
    assert tr["latest_call_date"] == "2026-11-09"
    assert tr["daily_calls"][0]["status"] == "pending" and tr["daily_calls"][0]["right"] is None
    assert tr["daily_calls"][1]["date"] == "2026-11-06"
