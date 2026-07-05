"""Income book store and builder tests."""
from __future__ import annotations

from signals.income_book_builder import (
    compute_goal_summary,
    candidate_from_row,
    pick_diversified_candidates,
    refresh_open_trade,
)
from signals.income_book_store import (
    close_trade,
    default_book,
    enter_trade,
    update_settings,
)


def _swing_row(ticker="NET", score=78, setup="breakout", gates=4):
    return {
        "ticker": ticker,
        "close": 105.0,
        "swing_setup_type": setup,
        "swing_setup_label": "BREAKOUT",
        "swing_score": score,
        "swing_verdict": "SWING_SIGNAL",
        "swing_entry_low": 103.0,
        "swing_entry_high": 106.0,
        "swing_stop": 100.0,
        "swing_t1": 112.0,
        "swing_t2": 118.0,
        "swing_rr": 2.3,
        "retail_status": {
            "gates": [
                {"id": "valuation", "pass": True},
                {"id": "regime", "pass": gates >= 1},
                {"id": "momentum", "pass": gates >= 2},
                {"id": "ml", "pass": gates >= 3},
            ],
            "gates_locked_count": max(0, 4 - gates),
            "go_no_go": "go" if gates >= 4 else "no_go",
        },
        "gate_cleared": gates >= 4,
        "gates_passed": gates,
        "gates_total": 4,
    }


def test_goal_summary_feasibility():
    green = compute_goal_summary({"goal_usd": 5000, "capital_usd": 100000, "timeframe_months": 3})
    assert green["feasibility"] == "green"
    assert green["required_return_pct"] == 5.0
    red = compute_goal_summary({"goal_usd": 5000, "capital_usd": 25000, "timeframe_months": 1})
    assert red["feasibility"] == "red"


def test_candidate_excludes_held():
    row = _swing_row()
    c = candidate_from_row(row, config={}, settings={"capital_usd": 100000, "risk_pct": 1.5}, held_tickers={"NET"})
    assert c is None


def test_candidate_from_row():
    c = candidate_from_row(
        _swing_row(),
        config={"income_book": {"min_swing_score": 65, "min_gates_passed": 3}},
        settings={"capital_usd": 100000, "risk_pct": 1.5},
        held_tickers=set(),
    )
    assert c is not None
    assert c["ticker"] == "NET"
    assert c["sizing"]["shares"] > 0


def test_diversified_pick_sector_cap():
    candidates = [
        {"ticker": "A", "sector": "Tech", "swing_score": 80, "swing_rr": 2},
        {"ticker": "B", "sector": "Tech", "swing_score": 79, "swing_rr": 2},
        {"ticker": "C", "sector": "Tech", "swing_score": 77, "swing_rr": 2},
        {"ticker": "D", "sector": "Health", "swing_score": 76, "swing_rr": 2},
    ]
    picked = pick_diversified_candidates(candidates, limit=3, max_sector_slots=2)
    tickers = [p["ticker"] for p in picked]
    assert len(tickers) == 3
    assert tickers.count("A") + tickers.count("B") + tickers.count("C") <= 2


def test_enter_and_close_trade():
    book = default_book()
    update_settings(book, {"goal_usd": 5000, "capital_usd": 50000})
    enter_trade(book, ticker="NET", entry_price=105.0, shares=50, stop=100, t1=112)
    assert len(book["open_trades"]) == 1
    closed = close_trade(book, ticker="NET", exit_price=110.0)
    assert closed["realized_pnl_usd"] == 250.0
    assert len(book["open_trades"]) == 0
    assert len(book["closed_trades"]) == 1


def test_refresh_open_trade_trim():
    trade = {"ticker": "NET", "entry_price": 100, "shares": 10, "stop": 95, "t1": 110}
    row = {"close": 111, "swing_score": 70, "gate_cleared": True, "gates_passed": 4, "gates_total": 4}
    out = refresh_open_trade(trade, row)
    assert out["today_action"] == "trim_t1"
    assert out["unrealized_pnl_usd"] == 110.0
