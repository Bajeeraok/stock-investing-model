"""Tests for free institutional ownership fallbacks (Yahoo + SEC EDGAR 13F)."""
from __future__ import annotations

import pandas as pd

from signals import institutional_signals as ins
from signals import yahoo_institutional as yi


def test_parse_major_holders():
    df = pd.DataFrame(
        [
            ["insidersPercentHeld", 0.04],
            ["institutionsPercentHeld", 0.71],
            ["institutionsFloatPercentHeld", 0.74],
            ["institutionsCount", 7548.0],
        ]
    )
    out = yi._parse_major_holders(df)
    assert out["institutions_pct"] == 71.0
    assert out["institutions_count"] == 7548


def test_trend_from_holder_changes():
    holders = [
        {"pct_change_qoq": 2.0},
        {"pct_change_qoq": -1.5},
        {"pct_change_qoq": 0.8},
    ]
    trend = yi._trend_from_holder_changes(holders)
    assert trend["trend"] in ("ACCUMULATING", "NEUTRAL", "DISTRIBUTING")
    assert trend["total_institutions"] == 3


def test_institutional_trend_prefers_yahoo(monkeypatch):
    monkeypatch.setattr(
        ins,
        "fetch_institutional_holder_summary",
        lambda config, ticker: (None, "No FMP API key"),
    )
    monkeypatch.setattr(
        ins,
        "get_institutional_ownership",
        lambda ticker: {
            "institutional_pct": 70.0,
            "holder_trend": {
                "trend": "ACCUMULATING",
                "pct_institutions_increasing": 0.67,
                "total_institutions": 10,
            },
            "as_of": "2026-03-31",
        },
    )
    monkeypatch.setattr(ins, "get_edgar_13f_holder_snapshot", lambda ticker, config=None: {"trend": "NEUTRAL"})

    out = ins.get_institutional_trend_proxy({}, "NVDA")
    assert out["trend"] == "ACCUMULATING"
    assert out["source"] == "yfinance_delayed"


def test_build_institutional_bundle_shape(monkeypatch):
    monkeypatch.setattr(
        ins,
        "get_institutional_ownership",
        lambda ticker: {
            "institutional_pct": 65.5,
            "institutional_pct_label": "65.5%",
            "source": "yfinance_delayed",
            "source_note": "test",
            "top_holders": [{"holder": "Vanguard", "pct_held": 8.0}],
            "holder_trend": {"trend": "NEUTRAL", "pct_institutions_increasing": 0.5, "total_institutions": 4},
        },
    )
    monkeypatch.setattr(
        ins,
        "get_edgar_13f_holder_snapshot",
        lambda ticker, config=None, top_holders=None: {
            "trend": "ACCUMULATING",
            "period_ending": "2025-12-31",
            "top_holder_changes": [],
            "parser": "edgartools",
        },
    )
    monkeypatch.setattr(
        ins,
        "get_weighted_insider_signal",
        lambda config, ticker: {"signal": 0, "n": 0, "error": "No FMP API key"},
    )
    monkeypatch.setattr(
        ins,
        "get_short_interest_signal",
        lambda config, ticker: {"short_float_pct": 1.2, "signal": "LOW", "source": "yfinance_finra"},
    )

    bundle = ins.build_institutional_bundle({}, "AAPL")
    assert bundle["institutional_ownership"]["institutional_pct"] == 65.5
    assert bundle["institutional_trend"]["source"] == "yfinance_delayed"
    assert bundle["edgar_13f"]["period_ending"] == "2025-12-31"
    assert bundle["edgar_13f"]["parser"] == "edgartools"
    assert "conviction_filter" in bundle
    assert bundle["conviction_filter"]["role"] == "conviction_filter"


def test_edgar_trend_from_filer_rows():
    from signals.edgar_13f import _trend_from_rows

    rows = [
        {"change_pct": 3.0},
        {"change_pct": -2.5},
        {"change_pct": 0.5},
    ]
    trend, pct_inc, inc, dec = _trend_from_rows(rows)
    assert trend in ("ACCUMULATING", "NEUTRAL", "DISTRIBUTING")
    assert pct_inc is not None
    assert inc + dec <= len(rows)


def test_shares_for_ticker_aggregates():
    from signals.edgar_common import shares_for_ticker_in_report

    class FakeReport:
        holdings = pd.DataFrame(
            [
                {"Ticker": "NVDA", "SharesPrnAmount": 1000},
                {"Ticker": "NVDA", "SharesPrnAmount": 500},
                {"Ticker": "AAPL", "SharesPrnAmount": 200},
            ]
        )

    assert shares_for_ticker_in_report(FakeReport(), "NVDA") == 1500


def test_normalize_and_keyword_resolve():
    from signals.edgar_filer_resolve import _keyword_resolve, _normalize_holder_name

    assert _normalize_holder_name("Blackrock Inc.") == "BLACKROCK"
    hit = _keyword_resolve("Vanguard Capital Management LLC")
    assert hit is not None
    assert hit["cik"] == 102909


def test_resolve_filers_from_yahoo_holders(monkeypatch):
    from signals import edgar_filer_resolve as efr

    holders = [
        {"holder": "Blackrock Inc.", "pct_held": 7.9},
        {"holder": "State Street Corporation", "pct_held": 4.1},
    ]
    monkeypatch.setattr(
        efr,
        "resolve_holder_to_filer",
        lambda name, ticker, config=None, use_cache=True: efr._keyword_resolve(name),
    )
    filers, src = efr.resolve_filers_from_yahoo_holders(holders, "NVDA", {}, max_filers=5)
    assert src == "yahoo_dynamic"
    assert len(filers) >= 2
    ciks = {int(f["cik"]) for f in filers}
    assert 2012383 in ciks
    assert 93751 in ciks
