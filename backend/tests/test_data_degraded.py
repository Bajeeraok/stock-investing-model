from signals.data_degraded import build_degraded_sources, degraded_mode_active


def test_degraded_without_fmp_key():
    sources = build_degraded_sources({})
    assert degraded_mode_active(sources)
    fmp = next(s for s in sources if s["source"] == "FMP")
    assert fmp["status"] == "unavailable"
