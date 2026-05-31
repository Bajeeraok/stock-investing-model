from signals.velocity_engine import align_tactical_entry_with_one_answer


def test_breakout_watch_when_buy_horizon_but_hold_action():
    te = {"active": True, "velocity_triggered": True, "velocity_score": 95}
    oa = {"verdict": "BUY", "action_today": "hold"}
    out = align_tactical_entry_with_one_answer(te, oa)
    assert out["entry_stance"] == "breakout_watch"
    assert out["action_today"] == "hold"
    assert "not the same as enter" in (out.get("stance_note") or "")


def test_breakout_aligned_on_enter_now():
    te = {"active": True, "velocity_triggered": True}
    oa = {"verdict": "BUY", "action_today": "enter_now"}
    out = align_tactical_entry_with_one_answer(te, oa)
    assert out["entry_stance"] == "breakout_aligned"
