from signals.hunter_panel import build_hunter_panel, is_hunter_candidate


def test_is_hunter_candidate_velocity():
    assert is_hunter_candidate({"ticker": "NVDA", "track": "velocity", "velocity_triggered": True})
    assert not is_hunter_candidate({"ticker": "X", "readiness_tier": "watch"})


def test_is_hunter_candidate_readiness():
    assert is_hunter_candidate({"ticker": "AAPL", "readiness_tier": "go_ready"})
    assert is_hunter_candidate({"ticker": "MSFT", "readiness_tier": "almost_ready"})


def test_build_hunter_panel_sort_and_position():
    results = [
        {"ticker": "ZZZ", "readiness_tier": "warming", "readiness_score": 60, "close": 10},
        {"ticker": "AAA", "readiness_tier": "go_ready", "readiness_score": 100, "close": 20},
        {"ticker": "VEL", "track": "velocity", "velocity_triggered": True, "velocity_score": 80, "close": 5},
        {"ticker": "HOLD", "readiness_tier": "watch"},
    ]
    panel = build_hunter_panel(
        results,
        portfolio_tickers=["AAA"],
        watchlist_tickers=["ZZZ"],
        signal_universe=["AAA", "ZZZ", "VEL"],
    )
    assert panel["candidate_count"] == 3
    tickers = [c["ticker"] for c in panel["candidates"]]
    assert tickers[0] == "VEL"
    assert panel["candidates"][1]["ticker"] == "AAA"
    assert panel["candidates"][1]["position_status"] == "owned"
    assert panel["candidates"][2]["position_status"] == "watching"


def _panel(rows):
    return build_hunter_panel(rows, portfolio_tickers=[], watchlist_tickers=[], signal_universe=[])


def test_call_reconciles_gates_score_and_model():
    rows = [
        # 4/4 gates but model HOLD → wait, never "staged add"
        {"ticker": "REGN", "readiness_tier": "go_ready", "gate_cleared": True, "gates_passed": 4,
         "plan_action": "HOLD", "composite_buy": 72, "regime": "UP", "rsi": 55},
        # 4/4 + model BUY + healthy trend → buy
        {"ticker": "GOOD", "readiness_tier": "go_ready", "gate_cleared": True, "gates_passed": 4,
         "plan_action": "BUY", "composite_buy": 80, "regime": "UP", "rsi": 58},
        # oversold downtrend with weak score → avoid
        {"ticker": "IREN", "readiness_tier": "warming", "gates_passed": 3, "plan_action": "WATCH",
         "composite_buy": 10, "regime": "DOWN", "rsi": 22},
    ]
    by = {c["ticker"]: c for c in _panel(rows)["candidates"]}
    assert by["REGN"]["call"] == "wait"
    assert "HOLD" in by["REGN"]["call_reason"].upper()
    assert by["GOOD"]["call"] == "buy"
    assert by["IREN"]["call"] == "avoid"
    assert "knife" in by["IREN"]["call_reason"].lower()


def test_sort_within_tier_prefers_call_then_score():
    rows = [
        {"ticker": "LOW", "readiness_tier": "warming", "gates_passed": 3, "composite_buy": 12,
         "regime": "DOWN", "rsi": 25, "readiness_score": 80},
        {"ticker": "HIGH", "readiness_tier": "warming", "gates_passed": 3, "composite_buy": 70,
         "regime": "UP", "rsi": 50, "readiness_score": 70},
    ]
    tickers = [c["ticker"] for c in _panel(rows)["candidates"]]
    assert tickers == ["HIGH", "LOW"]


def test_model_avoid_moves_out_of_almost_ready():
    rows = [
        {"ticker": "MSFT", "readiness_tier": "almost_ready", "gates_passed": 3, "plan_action": "AVOID",
         "composite_buy": 77, "regime": "UP", "rsi": 57},
        {"ticker": "GS", "readiness_tier": "almost_ready", "gates_passed": 3, "plan_action": "HOLD",
         "composite_buy": 66, "regime": "UP", "rsi": 34},
    ]
    panel = _panel(rows)
    by = {c["ticker"]: c for c in panel["candidates"]}
    assert by["MSFT"]["display_tier"] == "avoid"
    assert by["GS"]["display_tier"] == "almost_ready"
    assert panel["counts"]["avoid"] == 1
