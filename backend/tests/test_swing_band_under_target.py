from signals.horizon_entry_calculator import _medium_term_signal_from_zone, MediumTermInputs
import dataclasses


def _inp(**kw):
    fields = {f.name for f in dataclasses.fields(MediumTermInputs)}
    base = dict(current_price=342.0, ma50=336.0, ma200=280.0, ml_prob=40.0, regime_bull_pct=60.0,
                fundamentals_score=50.0, options_sentiment_score=50.0, insider_activity_score=50.0, atr=8.0, pattern_score=50.0,
                days_to_earnings=None, fair_value=247.96)
    base.update(kw)
    return MediumTermInputs(**{k: v for k, v in base.items() if k in fields})


def test_band_above_fair_value_target_moves_under_target():
    sig = _medium_term_signal_from_zone(_inp(), 294.93, 336.01, "Acceptable", "#f5a623", "MA50 band", [])
    assert sig.entry_zone.high < sig.target
    assert sig.entry_zone.low < sig.entry_zone.high
    assert sig.verdict == "WAIT"
    assert any("No swing entry" in w for w in sig.warnings)


def test_band_partly_above_target_top_is_capped():
    sig = _medium_term_signal_from_zone(_inp(fair_value=300.0), 290.0, 336.01, "Acceptable", "#f5a623", "MA50 band", [])
    assert sig.entry_zone.low == 290.0
    assert sig.entry_zone.high <= sig.target / 1.05 + 0.01


def test_band_below_target_unchanged():
    sig = _medium_term_signal_from_zone(_inp(fair_value=400.0), 320.0, 336.01, "Acceptable", "#f5a623", "MA50 band", [])
    assert (sig.entry_zone.low, sig.entry_zone.high) == (320.0, 336.01)
