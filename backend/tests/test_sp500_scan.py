import numpy as np
import pandas as pd

from signals.sp500_scan import build_payload, row_from_bars


def _bars(drift: float, n: int = 260) -> pd.DataFrame:
    c = 100 * np.exp(np.cumsum(np.full(n, drift)))
    return pd.DataFrame({"Close": c, "Volume": np.full(n, 1e6)}, index=pd.bdate_range("2025-01-01", periods=n))


def test_rows_and_payload():
    up = row_from_bars("UPCO", _bars(0.003), "Tech")
    down = row_from_bars("DNCO", _bars(-0.003), "Energy")
    spy = row_from_bars("SPY", _bars(0.001), "ETF")
    assert up["price"] > up["ma50"] > up["ma200"] and down["price"] < down["ma200"]
    out = build_payload([up, down, spy], "2026-11-12T16:30:00-05:00")
    assert out["n_scanned"] == 3
    hits = {k: {h["ticker"] for h in v["hits"]} for k, v in out["rule_hits"].items()}
    assert "UPCO" in hits["trend_template"] and "DNCO" in hits["below_200d"]
    assert [r["ticker"] for r in out["leaders"]] == ["UPCO"]  # ETFs never listed as leaders
    assert out["leaders"][0]["rs_6m_vs_spy"] > 0


def test_short_history_skipped():
    assert row_from_bars("NEW", _bars(0.001, 100)) is None
