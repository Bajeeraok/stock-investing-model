def test_premarket_engine_imports():
    # A broken indent here silently froze the Pre-market panel on 2026-06-08 data for months.
    from signals.premarket_engine import PreMarketEngine
    from scripts.pre_market_scheduler import report_to_dict, run_premarket_snapshot

    assert callable(PreMarketEngine().run) and callable(report_to_dict) and callable(run_premarket_snapshot)
