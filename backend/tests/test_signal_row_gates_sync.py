"""Regression: the flat gates_passed/gates_total/gate_cleared fields on a live signals
row must match the authoritative retail_status.gates count.

Bug: enrich_dashboard_signal_row() never set row["gates_passed"] — it only sets
retail_status.gates / gates_locked_count. readiness_score.compute_readiness() assumes
gates_passed/gates_total are already "frozen" on the row (per its own docstring) and
defaults to 0 when they're missing, then that wrong 0 gets written back onto the row via
row.update(...) in run_daily.py, clobbering the real count. This broke two surfaces that
trust row["gates_passed"] as the first source of truth (see
web/lib/signalsTableAudit.ts::resolveGatesCount): the Signals table's "Gates #" column
and its min-gates filter both silently showed/filtered on 0 for every ticker, while the
ticker-detail page (which reads retail_status.gates directly) showed the correct count —
an observed real-world case: AMZN showed 0/4 (list) vs 2/4 (ticker detail) for the same
signal.

Fix: run_daily.py now calls tracking_gate.gate_snapshot_from_row() to backfill
gates_passed/gates_total/gate_cleared/go_no_go from retail_status.gates before calling
compute_readiness(). This test exercises that exact sequence.
"""

from __future__ import annotations

from signals.readiness_score import compute_readiness
from signals.retail_action_payload import enrich_dashboard_signal_row
from signals.tracking_gate import gate_snapshot_from_row


def _amzn_like_row() -> dict:
    """A row shaped like a real partial-gate case: valuation + regime blocked,
    momentum + ml passing — 2 of 4 primary gates, not 0 and not 4.
    """
    return {
        "ticker": "AMZN",
        "close": 254.98,
        "lt_band": {"low": 200.0, "high": 285.0},  # assessment lands short of the T1 MOS bar
        "confluence_score": 71.0,
        "composite_buy": 76.4,
        "rsi": 46.4,
        "ml_short_prob": 0.347,
        "plan_action": None,
        "signal": "WATCH",
        "_global_market_regime": "BULL",
    }


def test_gates_passed_missing_before_backfill_regresses_to_zero():
    """Documents the bug directly: without the backfill step, compute_readiness alone
    silently defaults an unset gates_passed to 0 even when the row is genuinely 2/4.
    """
    row = _amzn_like_row()
    enrich_dashboard_signal_row(row, regime_bull_pct=25.2)
    rs = row["retail_status"]
    primary = [g for g in rs["gates"] if g["id"] in ("valuation", "regime", "momentum", "ml")]
    real_passed = sum(1 for g in primary if g["pass"])
    assert 0 < real_passed < 4  # sanity: this is genuinely a partial-gate case, not 0 or 4

    # compute_readiness run directly on the freshly-enriched row, exactly as it would be
    # without the fix — gates_passed was never set, so it silently reads as 0.
    readiness = compute_readiness(row)
    assert readiness["gates_passed"] == 0
    assert readiness["gates_passed"] != real_passed  # the bug: silently wrong


def test_gate_snapshot_backfill_fixes_gates_passed_before_readiness():
    row = _amzn_like_row()
    enrich_dashboard_signal_row(row, regime_bull_pct=25.2)
    rs = row["retail_status"]
    primary = [g for g in rs["gates"] if g["id"] in ("valuation", "regime", "momentum", "ml")]
    real_passed = sum(1 for g in primary if g["pass"])

    # The fix: backfill from the authoritative source before compute_readiness runs.
    row.update(gate_snapshot_from_row(row))
    assert row["gates_passed"] == real_passed
    assert row["gates_total"] == 4

    readiness = compute_readiness(row)
    assert readiness["gates_passed"] == real_passed
    assert readiness["gate_cleared"] == row["gate_cleared"]


def test_full_go_row_still_reports_four_of_four():
    """Sanity check the fix doesn't regress the all-pass case."""
    row = {
        "ticker": "TESTFULLGO",
        "close": 100.0,
        "lt_band": {"low": 130.0, "high": 160.0},  # comfortably above close -> strong MOS
        "confluence_score": 80.0,
        "composite_buy": 80.0,
        "rsi": 35.0,
        "ml_short_prob": 0.60,
        "signal": "BUY",
    }
    enrich_dashboard_signal_row(row, regime_bull_pct=90.0)
    row.update(gate_snapshot_from_row(row))
    assert row["gates_passed"] == 4
    assert row["gates_total"] == 4
    assert row["gate_cleared"] is True
