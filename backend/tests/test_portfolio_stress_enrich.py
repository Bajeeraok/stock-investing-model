from signals.portfolio_stress import enrich_signal_uncertainty


def test_enrich_signal_uncertainty_mt_lt_narratives():
    row = {
        "close": 100.0,
        "st_band": {"low": 98.0, "high": 102.0},
        "mt_band": {"low": 90.0, "high": 110.0},
        "lt_band": {"low": 70.0, "high": 130.0},
        "lt_band_low_confidence": True,
        "atr_14": 2.0,
    }
    enrich_signal_uncertainty(row)
    u = row["uncertainty"]
    assert u.get("st_band_width_pct") == 4.0
    assert u.get("mt_band_width_pct") == 20.0
    assert "MT band" in (u.get("mt_narrative") or "")
    assert u.get("lt_band_width_pct") == 60.0
    assert "Wide fair-value" in (u.get("lt_narrative") or "")
