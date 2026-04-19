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
