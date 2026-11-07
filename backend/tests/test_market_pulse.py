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


PRE = "2026-10-30T09:20:01-04:00"


def test_score_days():
    calls = {
        "2026-10-30": {
            "pre_open": {"lean": "BEARISH", "p_close_red": 0.86, "eod_range_pct": {"q10": -2.15, "q90": 0.12}, "as_of": PRE},
            "10:30": {"p_close_green": 0.1, "likely_close_pct": -1.3, "range80_pct": [-2.2, -0.4]},
        },
        "2026-10-29": {"pre_open": {"lean": "MIXED", "p_close_red": 0.47, "eod_range_pct": {"q10": -0.67, "q90": 0.71}, "as_of": PRE}},
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


def test_pre_open_saved_after_open_is_not_scored():
    calls = {
        "2026-11-05": {
            "pre_open": {"lean": "BEARISH", "p_close_red": 0.88, "eod_range_pct": {"q10": -5.13, "q90": 0.19}},
            "10:30": {"p_close_green": 0.0, "likely_close_pct": -2.51, "range80_pct": [-3.0, -2.02]},
        },
        "2026-11-04": {"pre_open": {"lean": "BULLISH", "p_close_red": 0.05, "as_of": "2026-11-04T10:31:00-05:00"}},
    }
    realized = {"2026-11-05": {"gap_pct": -0.17, "full_pct": -4.41}, "2026-11-04": {"gap_pct": 1.15, "full_pct": 1.65}}
    sc = mp.score_days(calls, realized)
    assert sc["summary"]["pre_open"]["days"] == 0 and sc["summary"]["pre_open"]["direction_calls"] == 0
    assert sc["days"][0]["pre_open"]["late"] and sc["days"][0]["pre_open"]["hit"] is None
    # p_close_green == 0.0 is a RED call, not "missing"
    assert sc["days"][0]["10:30"]["call"] == "RED" and sc["days"][0]["10:30"]["hit"] is True


def test_ref_close_date_skips_weekends_and_holidays():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    et = ZoneInfo("America/New_York")
    d = lambda *a: mp._ref_close_date(datetime(*a, tzinfo=et)).isoformat()
    assert d(2026, 11, 6, 8, 15) == "2026-11-05"   # Fri pre-open → Thu close
    assert d(2026, 11, 9, 8, 15) == "2026-11-06"   # Mon pre-open → Fri close
    assert d(2026, 11, 6, 17, 0) == "2026-11-06"   # Fri evening → today's close
    assert d(2026, 11, 7, 12, 0) == "2026-11-06"   # Saturday → Fri close
    assert d(2026, 11, 27, 8, 0) == "2026-11-25"   # Fri after Thanksgiving → Wed close
    assert mp._close_label(mp._prev_session(datetime(2026, 11, 6).date())) == "Nov 5 close"


def test_pre_open_logged_only_before_open(tmp_path, monkeypatch):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    et = ZoneInfo("America/New_York")
    monkeypatch.setattr(mp, "_calls_dir", lambda: tmp_path)
    monkeypatch.setattr(mp, "_daily_last_two", lambda sym: (100.0, 98.0))
    monkeypatch.setattr(mp, "_spy_today", lambda now: (None, None, None))
    monkeypatch.setattr(mp, "_engine_bias_today", lambda day: None)
    monkeypatch.setattr(mp, "_last_bar_date", lambda sym: None)

    mp.build_market_pulse(log=True, now=datetime(2026, 11, 5, 10, 31, tzinfo=et))
    assert "pre_open" not in mp._load_day("2026-11-05")

    out = mp.build_market_pulse(log=True, now=datetime(2026, 11, 6, 9, 20, tzinfo=et))
    saved = mp._load_day("2026-11-06")["pre_open"]
    assert saved["as_of"].startswith("2026-11-06T09:20") and mp._pre_open_scorable(saved)
    assert saved["ref_close_date"] == "2026-11-05" and "vs Nov 5 close" in saved["note"]
    assert out["pre_open"]["ref_close_date"] == "2026-11-05"


def test_pre_open_range_scales_with_vix():
    calm = mp.pre_open_outlook(0.07, vix_level=15)
    stressed = mp.pre_open_outlook(0.07, vix_level=27)
    w = lambda o: o["eod_range_pct"]["q90"] - o["eod_range_pct"]["q10"]
    assert w(stressed) > 2 * w(calm) and stressed["range_vix_scaled"]
    assert stressed["p_close_red"] == calm["p_close_red"] == 0.47
    assert mp.pre_open_outlook(0.07)["eod_range_pct"] == {"q10": -0.67, "q50": 0.04, "q90": 0.71}


def test_due_slot_never_logs_late_job_under_earlier_slot():
    from datetime import datetime

    assert mp._due_intraday_slot(datetime(2026, 11, 6, 10, 31)) == "10:30"
    assert mp._due_intraday_slot(datetime(2026, 11, 6, 12, 31)) == "12:30"
    assert mp._due_intraday_slot(datetime(2026, 11, 6, 15, 31)) == "15:30"
    assert mp._due_intraday_slot(datetime(2026, 11, 6, 11, 20)) is None


def test_calibration_scores_hourly_slots_separately():
    calls = {"2026-11-06": {
        "10:30": {"p_close_green": 0.92, "range80_pct": [-0.1, 1.5]},
        "14:30": {"p_close_green": 0.97, "range80_pct": [0.1, 0.6]},
    }}
    realized = {"2026-11-06": {"gap_pct": 0.25, "full_pct": 0.31}}
    cal = mp.score_calibration(calls, realized)
    assert set(cal["by_slot"]) == {"10:30", "14:30"}
    assert cal["green_odds"][-1]["n"] == 2 and cal["green_odds"][-1]["closed_green_pct"] == 100.0
    assert "14:30" not in mp.score_days(calls, realized)["summary"]


def test_intraday_range_widens_faster_than_vix():
    lo20, hi20 = mp.intraday_close_range(0.0, 60, 20.0)["range80_pct"]
    lo40, hi40 = mp.intraday_close_range(0.0, 60, 40.0)["range80_pct"]
    assert (hi40 - lo40) > 2 * (hi20 - lo20)
