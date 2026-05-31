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
