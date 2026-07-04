"""EOD full-cohort detection after analysis-bundle regression (1ae1354)."""

from scripts.run_daily import (
    full_eod_snapshot_exists,
    maybe_save_eod_from_last_run,
    min_full_eod_row_count,
    save_eod_snapshot,
)


def test_min_full_eod_row_count():
    config = {"watchlist": ["A"] * 100, "portfolio": []}
    # Uses get_eod_signal_universe — just assert reasonable floor
    n = min_full_eod_row_count(config)
    assert n >= 50


def test_full_eod_snapshot_exists_counts_rows(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    from config_loader import load_config

    config = load_config()
    min_full = min_full_eod_row_count(config)
    thin = [{"ticker": f"T{i}", "composite_buy": 50} for i in range(10)]
    save_eod_snapshot(thin, date_str="2026-06-20", universe="dashboard_auto")
    assert full_eod_snapshot_exists("2026-06-20", config) is False

    full = [{"ticker": f"T{i}", "composite_buy": 50} for i in range(min_full)]
    save_eod_snapshot(full, date_str="2026-06-20", universe="eod")
    assert full_eod_snapshot_exists("2026-06-20", config) is True


def test_maybe_save_skips_dashboard_only_universe(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    from config_loader import get_data_root, load_config

    config = load_config()
    min_full = min_full_eod_row_count(config)
    last_run = {
        "run_results": [{"ticker": f"T{i}", "composite_buy": 50} for i in range(min_full - 5)],
    }
    path = get_data_root() / "last_run.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    import json

    path.write_text(json.dumps(last_run), encoding="utf-8")
    out = maybe_save_eod_from_last_run("2026-06-18")  # Thursday
    assert out.get("skipped") is True
    assert out.get("reason") == "dashboard_only_universe"
