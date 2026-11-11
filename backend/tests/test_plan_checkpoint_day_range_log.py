from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from signals.plan_checkpoint import latest_checkpoint, pin_session_bar

ET = ZoneInfo("America/New_York")


def _series():
    idx = pd.to_datetime(["2026-11-09", "2026-11-10", "2026-11-11"])
    close = pd.Series([100.0, 101.0, 95.0], index=idx)
    df = pd.DataFrame({"close": close, "high": [101, 102, 99.0], "low": [99, 100, 94.0]}, index=idx)
    return close, close * 0 + 1000, df


def test_checkpoints():
    assert latest_checkpoint(datetime(2026, 11, 11, 10, 29, tzinfo=ET)) is None
    assert latest_checkpoint(datetime(2026, 11, 11, 14, 45, tzinfo=ET)) == (14, 30)
    assert latest_checkpoint(datetime(2026, 11, 11, 15, 31, tzinfo=ET)) == (15, 30)


def test_before_1030_uses_previous_close():
    c, v, df = _series()
    c2, v2, df2, meta = pin_session_bar("X", c, v, df, now=datetime(2026, 11, 11, 10, 0, tzinfo=ET),
                                        bars_fn=lambda *a: {"close": 1, "high": 1, "low": 1})
    assert float(c2.iloc[-1]) == 101.0 and len(df2) == 2 and len(v2) == 2
    assert meta["label"] == "Nov 10 close" and meta["next"] == "10:30 AM ET"


def test_pinned_to_checkpoint_price_and_original_untouched():
    c, v, df = _series()
    bar = {"close": 97.5, "high": 99.0, "low": 94.0}
    c2, _, df2, meta = pin_session_bar("X", c, v, df, now=datetime(2026, 11, 11, 13, 5, tzinfo=ET),
                                       bars_fn=lambda *a: bar)
    assert float(c2.iloc[-1]) == 97.5 and float(df2["close"].iloc[-1]) == 97.5
    assert float(c.iloc[-1]) == 95.0 and float(df["close"].iloc[-1]) == 95.0
    assert meta["label"] == "12:30 PM ET" and meta["price"] == 97.5 and meta["next"] == "2:30 PM ET"


def test_outside_session_unchanged():
    c, v, df = _series()
    c2, _, _, meta = pin_session_bar("X", c, v, df, now=datetime(2026, 11, 11, 16, 30, tzinfo=ET))
    assert meta is None and float(c2.iloc[-1]) == 95.0


def test_score_snapshot_and_aggregate():
    from signals.day_range_log import aggregate, score_snapshot

    snap = {"close_low": 95, "close_high": 105, "close_low50": 98, "close_high50": 102, "close_mid": 100,
            "ladder": [{"p": 0.75, "dip": 99, "pop": 101}, {"p": 0.1, "dip": 95, "pop": 105}],
            "levels": [{"label": "Swing band low", "price": 97, "side": "below", "p_reach": 0.4, "p_close_beyond": 0.2}]}
    r = score_snapshot(snap, low=96.5, high=100.5, close=99.0)
    assert r["in80"] and r["in50"] and r["close_err_pct"] == -1.0
    assert [x["dip_hit"] for x in r["ladder"]] == [True, False] and not r["ladder"][0]["pop_hit"]
    assert r["levels"][0]["reached"] and not r["levels"][0]["closed_beyond"]
    agg = aggregate([{"scored": {"0920": {"X": r}}}])
    assert agg["0920"]["n"] == 1 and agg["0920"]["in80_pct"] == 100
    assert agg["0920"]["ladder"][0] == {"p": 0.75, "hit_pct": 50, "n": 2}


def test_log_and_score_day(tmp_path, monkeypatch):
    import signals.day_range_log as m
    import signals.stock_day_range as sdr

    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    monkeypatch.setattr(sdr, "compute_stock_day_range", lambda t, s=None, now=None: {
        "phase": "next_session", "close_low": 95, "close_high": 105, "close_mid": 100, "ladder": [], "levels": []})
    now = datetime(2026, 11, 11, 9, 20, tzinfo=ET)
    assert m.log_slot("0920", {}, tickers=["AAA"], now=now) == 1
    idx = pd.date_range("2026-11-11 09:30", periods=3, freq="5min", tz=ET)
    bars = pd.DataFrame({"Low": [98.0, 97.0, 99.0], "High": [101.0, 102.0, 100.0]}, index=idx)
    assert m.score_day("2026-11-11", bars_fn=lambda t, d: (bars, 103.0)) == 1
    assert m.score_day("2026-11-11", bars_fn=lambda t, d: (bars, 103.0)) == 0
    sc = m._load("2026-11-11")["scored"]["0920"]["AAA"]
    assert sc["in80"] and sc["low_after"] == 97.0
