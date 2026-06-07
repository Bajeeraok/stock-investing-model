"""Shell payload includes analysis-bundle keys after lazy load merge."""
from __future__ import annotations

from api.dashboard_shell import ANALYSIS_BUNDLE_KEYS, build_shell_from_full


def test_shell_passes_through_analysis_bundle_keys():
    full = {
        "as_of_date": "2026-06-07",
        "analysis_deferred": False,
        "model_audit": {"enabled": True, "cohort_size": 100},
        "forward_tracking": {"records": [{"ticker": "SPY"}], "summary_by_horizon": {}},
        "signals": [{"ticker": "SPY", "composite_buy": 55}],
    }
    shell = build_shell_from_full(full, include_full_signals=False)
    assert shell.get("analysis_deferred") is False
    assert shell.get("model_audit", {}).get("enabled") is True
    assert len(shell.get("forward_tracking", {}).get("records") or []) == 1
    for key in ANALYSIS_BUNDLE_KEYS:
        if key in full:
            assert key in shell


def test_shell_defaults_analysis_deferred_without_bundle():
    shell = build_shell_from_full({"as_of_date": "2026-06-07"}, include_full_signals=False)
    assert shell.get("analysis_deferred") is True
    assert "model_audit" not in shell
