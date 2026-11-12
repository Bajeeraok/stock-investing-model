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


def _long_series():
    idx = pd.bdate_range("2026-09-01", "2026-11-11")
    vals = [100.0 * (1.01 if i % 2 else 0.99) ** 1 for i in range(len(idx))]
    close = pd.Series(vals, index=idx)
    df = pd.DataFrame({"close": close, "high": close * 1.01, "low": close * 0.99}, index=idx)
    return close, df


def test_gap_day_refreshes_at_1000():
    c, df = _long_series()
    prev = float(c.iloc[-2])
    bar = {"open": prev * 1.08, "close": prev * 1.07, "high": prev * 1.09, "low": prev * 1.06}
    c2, _, _, meta = pin_session_bar("X", c, None, df, now=datetime(2026, 11, 11, 10, 5, tzinfo=ET),
                                     bars_fn=lambda *a: bar)
    assert meta["gap"] and meta["label"] == "10:00 AM ET (gap open)" and meta["next"] == "10:30 AM ET"
    assert round(float(c2.iloc[-1]), 4) == round(prev * 1.07, 4)


def test_no_gap_keeps_previous_close_until_1030():
    c, df = _long_series()
    prev = float(c.iloc[-2])
    bar = {"open": prev * 1.002, "close": prev * 1.005, "high": prev * 1.006, "low": prev}
    c2, _, _, meta = pin_session_bar("X", c, None, df, now=datetime(2026, 11, 11, 10, 15, tzinfo=ET),
                                     bars_fn=lambda *a: bar)
    assert meta["checkpoint"] is None and float(c2.iloc[-1]) == prev
    # Before 10:00 even a gap day uses the previous close.
    bar["open"] = prev * 1.2
    _, _, _, meta = pin_session_bar("X", c, None, df, now=datetime(2026, 11, 11, 9, 50, tzinfo=ET),
                                    bars_fn=lambda *a: bar)
    assert meta["checkpoint"] is None


def test_run_after_open_counts_as_gap():
    c, df = _long_series()
    prev = float(c.iloc[-2])
    bar = {"open": prev * 1.002, "close": prev * 1.06, "high": prev * 1.06, "low": prev}
    _, _, _, meta = pin_session_bar("X", c, None, df, now=datetime(2026, 11, 11, 10, 15, tzinfo=ET),
                                    bars_fn=lambda *a: bar)
    assert meta["gap"] and meta["label"] == "10:00 AM ET (gap open)"


def _bars(prices, lows=None):
    idx = pd.date_range("2026-11-12 09:30", periods=len(prices), freq="5min", tz=ET)
    lows = lows or prices
    return pd.DataFrame({"Open": prices, "High": prices, "Low": lows, "Close": prices}, index=idx)


def test_plan_event_big_move_and_cooldown():
    from signals.plan_checkpoint import find_plan_event

    now = datetime(2026, 11, 12, 11, 30, tzinfo=ET)
    px = [100.0] * 12 + [95.0] * 6 + [90.0] * 6  # 10:30 -> -5%, 11:00 -> -10%
    base = datetime(2026, 11, 12, 10, 0, tzinfo=ET)
    ev = find_plan_event(_bars(px), now=now, base_time=base, base_px=100.0, sigma=0.04,
                         stop_for=lambda k: None, base_key="k")
    assert ev["reason"] == "big move" and ev["close"] == 90.0
    assert ev["time"].hour == 11 and ev["time"].minute == 5
    early = find_plan_event(_bars(px), now=datetime(2026, 11, 12, 10, 50, tzinfo=ET), base_time=base,
                            base_px=100.0, sigma=0.04, stop_for=lambda k: None, base_key="k")
    assert early["time"].minute == 35 and early["close"] == 95.0


def test_plan_event_stop_break_and_quiet_day():
    from signals.plan_checkpoint import find_plan_event

    now = datetime(2026, 11, 12, 11, 0, tzinfo=ET)
    px = [100.0] * 18
    lows = [100.0] * 14 + [97.5] + [100.0] * 3
    base = datetime(2026, 11, 12, 10, 0, tzinfo=ET)
    ev = find_plan_event(_bars(px, lows), now=now, base_time=base, base_px=100.0, sigma=0.04,
                         stop_for=lambda k: 98.0 if k == "k" else None, base_key="k")
    assert ev["reason"] == "stop break" and ev["low"] == 97.5
    assert find_plan_event(_bars(px), now=now, base_time=base, base_px=100.0, sigma=0.04,
                           stop_for=lambda k: None, base_key="k") is None


def test_pin_uses_event_rebuild():
    c, v, df = _long_series_for_event()
    px = [c.iloc[-2]] * 12 + [c.iloc[-2] * 0.85] * 6
    c2, _, _, meta = pin_session_bar("X", c, v, df, now=datetime(2026, 11, 12, 11, 0, tzinfo=ET),
                                     bars_fn=lambda *a: None, session_fn=lambda t, n: _bars(px))
    assert meta["event"] == "big move" and meta["label"] == "10:35 AM ET (big move)"
    assert abs(float(c2.iloc[-1]) - c.iloc[-2] * 0.85) < 1e-6


def _long_series_for_event():
    import numpy as np

    idx = pd.bdate_range(end="2026-11-12", periods=40)
    close = pd.Series(100 * np.exp(0.02 * np.array([(-1) ** i for i in range(40)])), index=idx)
    df = pd.DataFrame({"close": close, "high": close, "low": close}, index=idx)
    return close, close * 0 + 1000, df
