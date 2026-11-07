import json

from signals.signal_audit_store import gate_outcome_scorecard_from_rows


def _g(**fails):
    return json.dumps([{"id": g, "pass": not fails.get(g, False)} for g in ("valuation", "regime", "momentum", "ml")])


def test_scorecard_groups_single_gate_blocks_by_month_and_dedupes_tickers():
    rows = [
        {"signal_date": "2026-10-01", "ticker": "A", "gate_detail_json": _g(), "return_30d_pct": 5, "benchmark_return_30d_pct": 2},
        {"signal_date": "2026-10-02", "ticker": "B", "gate_detail_json": _g(regime=True), "return_30d_pct": -1, "benchmark_return_30d_pct": 2},
        {"signal_date": "2026-10-03", "ticker": "B", "gate_detail_json": _g(regime=True), "return_30d_pct": 9, "benchmark_return_30d_pct": 2},
        {"signal_date": "2026-10-03", "ticker": "C", "gate_detail_json": _g(regime=True, ml=True), "return_30d_pct": 9, "benchmark_return_30d_pct": 2},
        {"signal_date": "2026-09-15", "ticker": "D", "gate_detail_json": _g(valuation=True), "return_30d_pct": 4, "benchmark_return_30d_pct": 1},
    ]
    sc = gate_outcome_scorecard_from_rows(rows)
    oct_ = sc["months"][0]
    assert oct_["month"] == "2026-10"
    assert oct_["all_pass"] == {"n": 1, "avg_vs_spy_pts": 3.0, "beat_spy_pct": 100.0}
    assert oct_["regime"] == {"n": 1, "avg_vs_spy_pts": -3.0, "beat_spy_pct": 0.0}
    assert oct_["ml"] is None
    assert sc["months"][1]["valuation"]["n"] == 1
    assert sc["overall"]["regime"]["n"] == 1
