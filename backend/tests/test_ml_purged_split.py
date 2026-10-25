from signals.ml_models import purged_split_bounds


def test_purged_split_has_gaps_and_no_overlap():
    tr_end, va_start, va_end, te_start = purged_split_bounds(1000, 20)
    assert tr_end < va_start < va_end < te_start <= 1000
    assert va_start - tr_end == 20
    assert te_start - va_end == 20
