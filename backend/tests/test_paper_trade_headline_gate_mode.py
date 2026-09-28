"""
Paper trading headline win-rate must reflect genuinely gate-cleared (full_go) conviction,
not a blend diluted by starter_only (partial-size) rows. Regression for the reported case:
the "accumulate" track's headline read 34.9% because 212 of ~237 logged rows were
starter_only, while forward-tracking's own gate-count-vs-win-rate curve shows lower-gate
cohorts underperform materially — blending them into "the" number understated what a fully
gate-cleared entry actually does. starter_only rows are NOT dropped from logging or from
the detailed by_gate_mode breakdown; only the headline aggregate changes basis.
"""
from __future__ import annotations

from signals.paper_trade_logger import PaperTradeLogger, _result_to_paper_record


def _rec(logger, ticker, *, gate_mode, outcome, ret, day):
    rec = _result_to_paper_record(
        {
            "ticker": ticker,
            "close": 100.0,
            "signal": "BUY",
            "st_band": {"low": 95.0, "high": 110.0},
            "entry_mode": gate_mode,
        },
        f"2027-01-{day:02d}",
    )
    assert rec is not None
    rec["gate_mode"] = gate_mode
    rec["outcome"] = outcome
    rec["hit_target"] = "1" if outcome == "HIT" else "0"
    rec["return_pct"] = str(ret)
    rec["next_date"] = f"2027-02-{day:02d}"
    return rec


def test_headline_uses_full_go_only_not_starter_only_blend(tmp_path):
    logger = PaperTradeLogger(data_root=tmp_path)
    rows = []
    day = 1
    # 3 full_go rows, all wins — this is what the headline should reflect.
    for _ in range(3):
        rows.append(_rec(logger, f"GO{day}", gate_mode="full_go", outcome="HIT", ret=3.0, day=day))
        day += 1
    # 10 starter_only rows, mostly losses — must NOT drag the headline down.
    for i in range(10):
        outcome = "HIT" if i < 3 else "MISS"
        rows.append(_rec(logger, f"ST{day}", gate_mode="starter_only", outcome=outcome, ret=1.0 if outcome == "HIT" else -2.0, day=day))
        day += 1
    logger._write_all(rows)

    summ = logger.get_performance_summary(min_completed=3, min_actionable=3)
    assert summ["headline_track"] == "accumulate_go"
    assert summ["win_rate_pct"] == 100.0  # only the 3 full_go wins count toward headline
    assert summ["completed_n"] if "completed_n" in summ else True

    # starter_only rows are still visible in the broader breakdown, not dropped.
    acc = summ.get("accumulate_summary") or {}
    assert acc["completed_n"] == 13  # 3 full_go + 10 starter_only
    by_gm = summ.get("by_gate_mode") or {}
    assert by_gm["starter_only"]["n"] == 10
    assert by_gm["full_go"]["n"] == 3


def test_falls_back_to_broader_accumulate_when_full_go_too_thin(tmp_path):
    logger = PaperTradeLogger(data_root=tmp_path)
    rows = []
    day = 1
    # Only 1 full_go row — below the headline floor — plus enough starter_only rows.
    rows.append(_rec(logger, "GO1", gate_mode="full_go", outcome="HIT", ret=3.0, day=day))
    day += 1
    for i in range(5):
        outcome = "HIT" if i < 2 else "MISS"
        rows.append(_rec(logger, f"ST{day}", gate_mode="starter_only", outcome=outcome, ret=1.0 if outcome == "HIT" else -1.0, day=day))
        day += 1
    logger._write_all(rows)

    summ = logger.get_performance_summary(min_completed=3, min_actionable=3)
    # Full_go alone (n=1) is too thin for the headline floor -> falls back to the broader
    # accumulate cohort (n=6) rather than starving the headline entirely.
    assert summ["headline_track"] == "accumulate"
    assert "too thin" in (summ.get("message") or "").lower()


def test_marketing_note_reflects_full_go_definition(tmp_path):
    logger = PaperTradeLogger(data_root=tmp_path)
    rows = [_rec(logger, f"GO{i}", gate_mode="full_go", outcome="HIT", ret=2.0, day=i + 1) for i in range(3)]
    logger._write_all(rows)
    summ = logger.get_performance_summary(min_completed=3, min_actionable=3)
    assert "full_go" in summ["marketing_note"]
    assert "starter_only" in summ["marketing_note"]
