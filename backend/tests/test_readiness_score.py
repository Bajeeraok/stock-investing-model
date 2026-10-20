from signals.readiness_score import compute_readiness, st_verdict_supports_add


def test_st_verdict_from_short_suggestion():
    assert st_verdict_supports_add({"short_suggestion": "HOLD/ADD"}) is True
    assert st_verdict_supports_add({"short_suggestion": "HOLD"}) is False


def test_almost_ready_three_gates_and_st():
    r = compute_readiness(
        {
            "gates_passed": 3,
            "gates_total": 4,
            "gate_cleared": False,
            "go_no_go": "no_go",
            "short_suggestion": "HOLD/ADD",
        }
    )
    assert r["readiness_tier"] == "almost_ready"
    assert r["almost_ready"] is True
    assert r["go_ready"] is False


def test_go_ready_four_gates():
    r = compute_readiness({"gates_passed": 4, "gates_total": 4, "gate_cleared": True})
    assert r["readiness_tier"] == "go_ready"
    assert r["go_ready"] is True


def test_warming_three_gates_no_st_buy():
    r = compute_readiness(
        {
            "gates_passed": 3,
            "gates_total": 4,
            "gate_cleared": False,
            "short_suggestion": "HOLD",
        }
    )
    assert r["readiness_tier"] == "warming"
    assert r["almost_ready"] is False


def test_falling_knife_not_almost_ready():
    """IREN-style: 3/4 gates + oversold-bounce ADD, but score 10 / RSI 22 / DOWN → warming, flagged."""
    r = compute_readiness(
        {
            "gates_passed": 3,
            "gates_total": 4,
            "gate_cleared": False,
            "short_suggestion": "HOLD/ADD",
            "composite_buy": 10,
            "rsi": 22,
            "regime": "DOWN",
        }
    )
    assert r["readiness_tier"] == "warming"
    assert r["falling_knife"] is True
