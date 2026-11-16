from datetime import date

import pandas as pd

from signals import best_setups


def _bars(closes, start="2026-11-09"):
    idx = pd.bdate_range(start, periods=len(closes))
    return pd.DataFrame({"close": closes, "high": closes, "low": closes}, index=idx)


def test_track_splits_pre_fix_and_reports_vs_spy(monkeypatch):
    hist = [
        {"as_of": "2026-11-10", "modes": {"swing": {"picks": [{"ticker": "AAA", "price": 100, "target": 150, "stop": 80}]}}},
        {"as_of": "2026-11-16", "modes": {"swing": {"picks": [{"ticker": "BBB", "price": 100, "target": 150, "stop": 80}]}}},
    ]
    monkeypatch.setattr(best_setups, "_history", lambda days=180: hist)
    monkeypatch.setattr(best_setups, "_market_today", lambda: date(2026, 11, 20))
    bars = {
        "SPY": _bars([100, 100, 100, 100, 100, 100, 99, 98, 98, 98]),
        "AAA": _bars([100, 100, 95, 95, 95, 95, 95, 95, 95, 95]),
        "BBB": _bars([100, 100, 100, 100, 100, 100, 100, 101, 102, 102]),
    }
    tr = best_setups.track_record(fetch=lambda t, p: bars[t])["swing"]
    assert tr["picks"] == 1 and tr["rules_since"] == best_setups.RULES_FIX_DATE
    assert tr["avg_vs_spy_pts"] is not None and tr["avg_vs_spy_pts"] > 0
    assert tr["before_fix"]["picks"] == 1 and tr["before_fix"]["avg_return_pct"] < 0
    assert {r["ticker"]: r["pre_fix"] for r in tr["recent"]} == {"AAA": True, "BBB": False}
