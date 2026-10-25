import pandas as pd

from signals.alpha.fundamental_factors import add_fund_score, factors_as_of, parse_companyfacts


def _q(start, end, val, filed, form="10-Q"):
    return {"start": start, "end": end, "val": val, "filed": filed, "form": form}


def _facts(concepts: dict[str, list[dict]], unit="USD") -> dict:
    return {"facts": {"us-gaap": {c: {"units": {unit: rows}} for c, rows in concepts.items()}}}


QUARTERS = [
    ("2021-01-01", "2021-03-31", "2021-05-01"),
    ("2021-04-01", "2021-06-30", "2021-08-01"),
    ("2021-07-01", "2021-09-30", "2021-11-01"),
    ("2021-10-01", "2021-12-31", "2022-02-15"),
    ("2022-01-01", "2022-03-31", "2022-05-01"),
    ("2022-04-01", "2022-06-30", "2022-08-01"),
]


def test_alias_stitching_prefers_full_history():
    old = [_q(s, e, 100.0, f) for s, e, f in QUARTERS[:3]]
    new = [_q(s, e, 120.0, f) for s, e, f in QUARTERS[3:]]
    p = parse_companyfacts(_facts({"Revenues": old, "RevenueFromContractWithCustomerExcludingAssessedTax": new}))
    assert len(p["revenue"]) == 6


def test_point_in_time_ignores_facts_filed_after_as_of():
    q = [
        ("2020-01-01", "2020-03-31", "2020-05-01"),
        ("2020-04-01", "2020-06-30", "2020-08-01"),
        ("2020-07-01", "2020-09-30", "2020-11-01"),
        ("2020-10-01", "2020-12-31", "2021-02-15"),
        *QUARTERS,
    ]
    noise = [0.0, 0.3, -0.2, 0.1, 0.4, -0.1, 0.2, 0.5, -0.3, 0.6]
    eps = [_q(s, e, 1.0 + noise[i], f) for i, (s, e, f) in enumerate(q)]
    facts = {"facts": {"us-gaap": {"EarningsPerShareDiluted": {"units": {"USD/shares": eps}}}}}
    p = parse_companyfacts(facts)
    early = factors_as_of(p, "2022-04-15")  # Q1-2022 (filed 2022-05-01) not yet public
    late = factors_as_of(p, "2022-08-15")
    assert early["days_since_filing"] == (pd.Timestamp("2022-04-15") - pd.Timestamp("2022-02-15")).days
    assert late["days_since_filing"] == (pd.Timestamp("2022-08-15") - pd.Timestamp("2022-08-01")).days
    assert early["sue"] is not None and early["sue"] != late["sue"]


def test_ytd_cumulative_values_become_quarterly():
    rows = [
        _q("2021-01-01", "2021-03-31", 10.0, "2021-05-01"),
        _q("2021-01-01", "2021-06-30", 25.0, "2021-08-01"),  # 6M YTD -> Q2 = 15
        _q("2021-01-01", "2021-09-30", 45.0, "2021-11-01"),  # 9M YTD -> Q3 = 20
        _q("2021-01-01", "2021-12-31", 70.0, "2022-02-15", form="10-K"),  # FY -> Q4 = 25
    ]
    q = parse_companyfacts(_facts({"NetIncomeLoss": rows}))["net_income"].set_index("end")["val"]
    assert list(q.round(6)) == [10.0, 15.0, 20.0, 25.0]


def test_fund_score_is_cross_sectional_percentile_mean():
    df = pd.DataFrame({
        "as_of_date": ["d"] * 3,
        "sue": [1.0, 2.0, 3.0], "rev_growth": [0.1, 0.2, 0.3],
        "gross_prof": [None] * 3, "roa": [None] * 3, "low_accruals": [None] * 3,
    })
    out = add_fund_score(df)
    assert out["fund_score"].is_monotonic_increasing and out["fund_score"].iloc[-1] == 100
    assert add_fund_score(df, min_factors=3)["fund_score"].isna().all()
