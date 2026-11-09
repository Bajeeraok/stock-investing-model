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
    monkeypatch.setattr(mp, "_session_bars", lambda sym, now: (None, None, None))
    monkeypatch.setattr(mp, "_ref_close", lambda sym, d: {"SPY": 680.0, "QQQ": 600.0}[sym])

    mp.build_market_pulse(log=True, now=datetime(2026, 11, 5, 10, 31, tzinfo=et))
    assert "pre_open" not in mp._load_day("2026-11-05")

    out = mp.build_market_pulse(log=True, now=datetime(2026, 11, 6, 9, 20, tzinfo=et))
    saved = mp._load_day("2026-11-06")["pre_open"]
    assert saved["as_of"].startswith("2026-11-06T09:20") and mp._pre_open_scorable(saved)
    assert saved["ref_close_date"] == "2026-11-05" and "vs Nov 5 close" in saved["note"]
    assert out["pre_open"]["ref_close_date"] == "2026-11-05"
    assert saved["levels"]["prev_close"] == 680.0 and saved["levels"]["expected_open"] == 666.4
    assert out["qqq"]["pre_open"]["levels"]["prev_close"] == 600.0
    assert "qqq_pre_open" in mp._load_day("2026-11-06")


def test_pre_open_uses_prior_vix_close_not_overnight_print(tmp_path, monkeypatch):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    monkeypatch.setattr(mp, "_calls_dir", lambda: tmp_path)
    monkeypatch.setattr(mp, "_daily_last_two",
                        lambda sym: (25.64, 23.25) if sym == "^VIX" else (100.0, 100.81))
    monkeypatch.setattr(mp, "_engine_bias_today", lambda day: None)
    monkeypatch.setattr(mp, "_ref_close", lambda sym, d: 700.0)
    out = mp.build_market_pulse(now=datetime(2026, 11, 9, 9, 20, tzinfo=ZoneInfo("America/New_York")))
    assert out["pre_open"]["vix_bucket"] == [25.0, 30.0]
    assert "Sized for VIX 25.6" in out["pre_open"]["note"]
    assert out["vix"]["last"] == 23.25


def test_pre_open_range_scales_with_vix():
    calm = mp.pre_open_outlook(0.07, vix_level=15)
    stressed = mp.pre_open_outlook(0.07, vix_level=27)
    w = lambda o: o["eod_range_pct"]["q90"] - o["eod_range_pct"]["q10"]
    assert w(stressed) > 2 * w(calm) and stressed["range_vix_scaled"]
    assert stressed["vix_bucket"] == [25.0, 30.0] and calm["vix_bucket"] == [0.0, 15.0]
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


def test_gap_up_red_odds_rise_with_vix():
    calm = mp.pre_open_outlook(0.43, vix_level=14)
    stressed = mp.pre_open_outlook(0.43, vix_level=25.6)
    assert calm["p_close_red"] < 0.2 < 0.3 < stressed["p_close_red"]
    assert stressed["p_close_red_all_vix"] == 0.22 and "VIX 25–30" in stressed["note"]
    assert mp.pre_open_outlook(0.43)["p_close_red"] == 0.22 and mp.pre_open_outlook(0.43)["vix_bucket"] is None


def test_pre_open_levels_in_dollars_and_qqq_table():
    o = mp.pre_open_outlook(0.5, vix_level=18, symbol="QQQ", ref_close=600.0)
    lv = o["levels"]
    assert lv["prev_close"] == 600.0 and lv["expected_open"] == 603.0
    assert lv["close_low"] < lv["close_mid"] < lv["close_high"]
    assert o["symbol"] == "QQQ" and "QQQ closed red" in o["note"]
    assert mp.pre_open_outlook(0.5)["levels"] is None
    assert mp.price_levels(None, 0.1, -1, 0, 1) is None


def test_qqq_keyed_on_prior_vxn_not_vix(tmp_path, monkeypatch):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    closes = {"^VIX": (25.64, 23.25), "^VXN": (34.02, 31.0)}
    monkeypatch.setattr(mp, "_calls_dir", lambda: tmp_path)
    monkeypatch.setattr(mp, "_daily_last_two", lambda sym: closes.get(sym, (100.0, 100.81)))
    monkeypatch.setattr(mp, "_engine_bias_today", lambda day: None)
    monkeypatch.setattr(mp, "_ref_close", lambda sym, d: 700.0)
    out = mp.build_market_pulse(now=datetime(2026, 11, 9, 9, 20, tzinfo=ZoneInfo("America/New_York")))
    q = out["qqq"]["pre_open"]
    assert q["vol_index"] == "VXN" and q["vix_bucket"] == [30.0, 999.0]
    assert "VXN over 30" in q["note"] and "Sized for VXN 34.0" in q["note"]
    assert "VXN at 34.0" in q["risk_reasons"]
    assert out["pre_open"]["vol_index"] == "VIX" and out["pre_open"]["vix_bucket"] == [25.0, 30.0]
    assert out["vxn"]["prev_close"] == 34.02


def test_daily_log_predicted_vs_actual():
    pre = {"as_of": "2026-11-09T09:20:00-05:00", "lean": "BULLISH", "p_close_red": 0.12, "vol_index": "VIX",
           "expected_gap_pct": 0.81, "eod_range_pct": {"q10": -0.15, "q50": 1.1, "q90": 1.84},
           "levels": {"prev_close": 735.29, "expected_open": 741.25, "close_low": 734.19, "close_mid": 743.38,
                      "close_high": 748.82}}
    late = {**pre, "as_of": "2026-11-06T09:45:00-05:00"}
    calls = {"2026-11-09": {"pre_open": pre}, "2026-11-06": {"pre_open": late}}
    realized = {"SPY": {"2026-11-09": {"prev_close": 735.29, "open": 741.95, "close": 752.64, "full_pct": 2.36},
                        "2026-11-06": {"prev_close": 733.0, "open": 734.82, "close": 735.29, "full_pct": 0.31}}}
    out = mp.daily_log(calls, realized)
    assert len(out["days"]) == 1  # late call not scored
    r = out["days"][0]
    assert r["range_result"] == "above" and r["direction_right"] is True
    assert r["open_err_pct"] == round((741.95 / 741.25 - 1) * 100, 2)
    s = out["summary"]["SPY"]
    assert s["in_range_pct"] == 0.0 and s["closed_above"] == 1 and s["direction_right_pct"] == 100.0


def test_key_levels_nearest_support_resistance():
    bars = [{"date": f"2026-10-{d:02d}", "high": 100 + d, "low": 95 + d, "close": 98 + d} for d in range(1, 21)]
    bars.append({"date": "2026-10-21", "high": 125.0, "low": 117.0, "close": 119.0})
    kl = mp.key_levels(bars, "2026-10-20", 118.5)
    assert kl["ref_close_date"] == "2026-10-20"
    assert all(x["price"] < 118.5 for x in kl["support"]) and all(x["price"] > 118.5 for x in kl["resistance"])
    assert kl["support"][0]["price"] > kl["support"][1]["price"]
    assert kl["resistance"][0]["price"] < kl["resistance"][1]["price"]
    assert "prev close" in kl["support"][0]["labels"]  # 118.0
    assert any("prev high" in x["labels"] for x in kl["resistance"])  # 120 = prev high = 5/20-day high
    live = mp.key_levels(bars, "2026-10-20", 122.0, today="2026-10-21")
    assert any("today's high" in x["labels"] for x in live["resistance"])
    assert mp.key_levels(bars[:1], "2026-10-01", 100.0) is None
