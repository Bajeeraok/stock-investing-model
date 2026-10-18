"""Scanner horizon_levels sync from signal rows."""
import json
from pathlib import Path

from scanner.horizon_levels import read_horizon_levels, sync_horizon_levels_from_signal_results


def test_sync_writes_bands_and_ml(tmp_path: Path):
    results = [
        {
            "ticker": "SPY",
            "close": 500.0,
            "st_band": {"low": 490.0, "high": 510.0},
            "mt_band": {"low": 480.0, "high": 520.0},
            "ml_short_prob": 0.42,
        }
    ]
    n = sync_horizon_levels_from_signal_results(tmp_path, results)
    assert n == 1
    levels = read_horizon_levels(tmp_path)
    spy = levels.get("SPY") or {}
    assert "short" in spy and "medium" in spy
    assert spy["short"]["entry_low"] == 490.0
    assert spy["short"]["target"] == 510.0
    ml_path = tmp_path / "scanner" / "ml_probs.json"
    assert ml_path.exists()
    mp = json.loads(ml_path.read_text())
    assert mp.get("SPY") == 42.0


def test_refresh_rr_also_rederives_rr_from_entry_after_target_move():
    """Scenario-target sync moves the target after the edge pass set risk_reward_from_entry;
    both R:R fields must follow the painted levels (HAL showed 3.1 from-entry vs 11.7 spot)."""
    from signals.horizon_entry_calculator import refresh_horizon_rr_from_levels
    from signals.scenario_target import sync_medium_horizon_target

    h = {
        "entry_zone": {"low": 33.03, "high": 34.39},
        "stop_loss": 32.01,
        "target": 38.0,
        "risk_reward_from_entry": 2.5,
    }
    horizons = {"medium": h}
    sync_medium_horizon_target(horizons, 50.88, spot=33.50)
    mid = (33.03 + 34.39) / 2
    expected = round((50.88 - mid) / (mid - 32.01), 2)
    assert h["target"] == 50.88
    assert abs(h["risk_reward_from_entry"] - expected) < 0.01
    # spot-based field refreshed too
    refresh_horizon_rr_from_levels(h, 33.50)
    assert h["risk_reward"] > h["risk_reward_from_entry"]
