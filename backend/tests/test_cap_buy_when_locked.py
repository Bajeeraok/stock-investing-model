from api.ticker_detail import cap_buy_verdicts_when_locked


def _out(mode, ov="BUY", lv="BUY"):
    return {"retail_action": {"entry_mode": mode}, "overall_verdict": ov,
            "horizons": {"short": {"verdict": "WAIT"}, "medium": {"verdict": "WATCH"}, "long": {"verdict": lv}}}


def test_locked_buy_becomes_watch():
    o = _out("hard_lock")
    cap_buy_verdicts_when_locked(o)
    assert o["overall_verdict"] == "WATCH" and o["model_overall_verdict"] == "BUY"
    assert o["horizons"]["long"]["verdict"] == "WATCH" and o["horizons"]["long"]["model_verdict"] == "BUY"
    assert o["horizons"]["short"]["verdict"] == "WAIT"


def test_unlocked_or_missing_mode_unchanged():
    for mode in ("full_go", "starter_only", None):
        o = _out(mode, "STRONG BUY")
        cap_buy_verdicts_when_locked(o)
        assert o["overall_verdict"] == "STRONG BUY" and "model_overall_verdict" not in o


def test_no_retail_action_is_safe():
    o = {"overall_verdict": "BUY"}
    cap_buy_verdicts_when_locked(o)
    assert o["overall_verdict"] == "BUY"
