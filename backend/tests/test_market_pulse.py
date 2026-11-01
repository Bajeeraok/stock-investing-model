from signals import market_pulse as mp


def test_pre_open_big_gap_down_is_bearish_high_risk():
    o = mp.pre_open_outlook(-1.2, vix_level=22, vix_pct=12)
    assert o["lean"] == "BEARISH" and o["p_close_red"] >= 0.8
    assert o["high_risk"] and len(o["risk_reasons"]) == 2
    assert o["eod_range_pct"]["q10"] < o["eod_range_pct"]["q90"]


def test_pre_open_flat_is_mixed():
    o = mp.pre_open_outlook(0.05)
    assert o["lean"] == "MIXED" and not o["high_risk"]
    assert mp.pre_open_outlook(None) is None


def test_intraday_range_narrows_through_the_day():
    early = mp.intraday_close_range(-0.8, 60, vix_prev=20)
    late = mp.intraday_close_range(-0.8, 330, vix_prev=20)
    w = lambda r: r["range80_pct"][1] - r["range80_pct"][0]
    assert w(late) < w(early)
    assert late["p_close_green"] < early["p_close_green"] < 0.5
    closed = mp.intraday_close_range(0.4, 390, vix_prev=20)
    assert closed["p_close_green"] == 1.0
    assert mp.intraday_close_range(0.1, 30, vix_prev=None) is None


def test_score_days():
    calls = {
        "2026-10-30": {
            "pre_open": {"lean": "BEARISH", "p_close_red": 0.86, "eod_range_pct": {"q10": -2.15, "q90": 0.12}},
            "10:30": {"p_close_green": 0.1, "likely_close_pct": -1.3, "range80_pct": [-2.2, -0.4]},
        },
        "2026-10-29": {"pre_open": {"lean": "MIXED", "p_close_red": 0.47, "eod_range_pct": {"q10": -0.67, "q90": 0.71}}},
    }
    realized = {"2026-10-30": {"gap_pct": -1.04, "full_pct": -1.77}, "2026-10-29": {"gap_pct": 0.1, "full_pct": -0.38}}
    sc = mp.score_days(calls, realized)
    pre = sc["summary"]["pre_open"]
    assert pre["days"] == 2 and pre["direction_calls"] == 1 and pre["direction_hit_pct"] == 100.0
    assert pre["range_coverage_pct"] == 100.0
    assert sc["summary"]["10:30"]["direction_hit_pct"] == 100.0
    assert sc["days"][0]["date"] == "2026-10-30"


def test_log_call_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(mp, "_calls_dir", lambda: tmp_path)
    assert mp.log_call("2026-11-02", "pre_open", {"lean": "MIXED"})
    assert not mp.log_call("2026-11-02", "pre_open", {"lean": "BEARISH"})
    assert mp._load_day("2026-11-02")["pre_open"]["lean"] == "MIXED"
