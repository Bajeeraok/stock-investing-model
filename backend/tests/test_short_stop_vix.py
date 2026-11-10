from signals.horizon_entry_calculator import ShortTermInputs, compute_short_term_entry


def _stop(vix):
    inp = ShortTermInputs(current_price=100.0, ml_prob=50.0, rsi=50.0, atr=4.0, vwap=99.0, support_level=95.0,
                          resistance_level=115.0, regime_bull_pct=60.0, pattern_score=50.0, volume_ratio=1.0, vix=vix)
    return compute_short_term_entry(inp).stop_loss


def test_short_stop_widens_with_vix_and_keeps_floor():
    base, high, calm = _stop(None), _stop(30.0), _stop(10.0)
    assert _stop(20.0) == base
    assert high < base
    assert calm >= base
