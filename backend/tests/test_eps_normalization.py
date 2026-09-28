"""
signals/eps_normalization.py — strips large one-time/non-operating swings (e.g. a
mark-to-market gain on equity investments) out of TTM EPS before it reaches the
fair-value model. Regression for the reported bug: Alphabet's Q2 included a ~$77.1B
gain on equity securities (Anthropic, SpaceX stakes) that inflated GAAP TTM EPS,
making TTM P/E look artificially cheap and inflating the fair-value estimate.
"""
from __future__ import annotations

from signals.eps_normalization import compute_core_ttm_eps


def _quarter(*, net_income, operating_income, other_income_expense_net,
             income_before_tax, income_tax_expense, shares=12_300_000_000, date="2026-06-30"):
    return {
        "date": date,
        "netIncome": net_income,
        "operatingIncome": operating_income,
        "totalOtherIncomeExpensesNet": other_income_expense_net,
        "incomeBeforeTax": income_before_tax,
        "incomeTaxExpense": income_tax_expense,
        "weightedAverageShsOutDil": shares,
    }


def _normal_quarter(date="2026-03-31"):
    """A quarter with routine, small other income (e.g. interest) — must not trigger."""
    return _quarter(
        net_income=22_045_700_000,
        operating_income=28_000_000_000,
        other_income_expense_net=300_000_000,
        income_before_tax=28_300_000_000,
        income_tax_expense=6_254_300_000,
        date=date,
    )


def _anomalous_quarter():
    """A quarter with a huge one-time gain on equity securities — the GOOGL case."""
    return _quarter(
        net_income=98_933_000_000,
        operating_income=28_000_000_000,
        other_income_expense_net=99_000_000_000,
        income_before_tax=127_000_000_000,
        income_tax_expense=28_067_000_000,
        date="2026-06-30",
    )


def test_no_adjustment_when_all_quarters_normal():
    rows = [_normal_quarter() for _ in range(4)]
    result = compute_core_ttm_eps(rows)
    assert result.adjusted is False
    assert result.anomalous_quarters == []
    assert result.gaap_ttm_eps == result.core_ttm_eps


def test_flags_and_strips_anomalous_quarter():
    rows = [_anomalous_quarter(), _normal_quarter(), _normal_quarter(), _normal_quarter()]
    result = compute_core_ttm_eps(rows)
    assert result.adjusted is True
    assert result.anomalous_quarters == ["2026-06-30"]
    assert result.gaap_ttm_eps > result.core_ttm_eps
    # Core EPS should land close to what after-tax operating income alone implies —
    # i.e. the one-time gain's contribution is removed, not just dampened.
    approx_core = round((28_000_000_000 * 0.779 * 4) / 12_300_000_000, 1)
    assert abs(result.core_ttm_eps - approx_core) < 1.0
    assert any("one-time" in n.lower() or "non-operating" in n.lower() for n in result.notes)


def test_small_other_income_does_not_trigger_even_if_relatively_large():
    """A tiny-operating-income quarter with a modest dollar swing must not trigger just
    because the swing is large *relative* to a near-zero operating income — the absolute
    threshold exists for exactly this case."""
    rows = [
        _quarter(
            net_income=100_000_000, operating_income=10_000_000,
            other_income_expense_net=50_000_000,  # 5x operating income, but tiny in dollars
            income_before_tax=60_000_000, income_tax_expense=12_000_000,
        ),
        _normal_quarter(), _normal_quarter(), _normal_quarter(),
    ]
    result = compute_core_ttm_eps(rows)
    assert result.adjusted is False


def test_large_absolute_swing_with_small_relative_ratio_does_not_trigger():
    """Symmetric guard: a $600M swing against $28B operating income (~2%) is routine for
    a mega-cap and must not trigger just because it clears the absolute-dollar threshold."""
    rows = [
        _quarter(
            net_income=22_500_000_000, operating_income=28_000_000_000,
            other_income_expense_net=600_000_000,
            income_before_tax=28_600_000_000, income_tax_expense=6_100_000_000,
        ),
        _normal_quarter(), _normal_quarter(), _normal_quarter(),
    ]
    result = compute_core_ttm_eps(rows)
    assert result.adjusted is False


def test_degrades_gracefully_with_fewer_than_four_quarters():
    result = compute_core_ttm_eps([_normal_quarter()])
    assert result.adjusted is False
    assert result.gaap_ttm_eps is None
    assert result.core_ttm_eps is None
    assert result.notes


def test_degrades_gracefully_with_no_data():
    result = compute_core_ttm_eps(None)
    assert result.adjusted is False
    assert result.gaap_ttm_eps is None


def test_missing_shares_degrades_gracefully():
    rows = [_normal_quarter() for _ in range(4)]
    for r in rows:
        r["weightedAverageShsOutDil"] = None
        r.pop("weightedAverageShsOut", None)
    result = compute_core_ttm_eps(rows)
    assert result.gaap_ttm_eps is None
    assert result.core_ttm_eps is None
