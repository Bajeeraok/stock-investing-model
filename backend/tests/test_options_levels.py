from datetime import date

import pandas as pd

from signals import options_levels as ol


def _chain(price=100.0):
    strikes = [90.0, 95.0, 100.0, 105.0, 110.0]
    calls = pd.DataFrame({"strike": strikes, "bid": [10.4, 5.9, 2.9, 1.0, 0.3], "ask": [10.6, 6.1, 3.1, 1.2, 0.4],
                          "lastPrice": [10.5, 6.0, 3.0, 1.1, 0.35], "openInterest": [10, 50, 900, 4000, 2500]})
    puts = pd.DataFrame({"strike": strikes, "bid": [0.3, 0.9, 2.9, 5.9, 10.4], "ask": [0.4, 1.1, 3.1, 6.1, 10.6],
                         "lastPrice": [0.35, 1.0, 3.0, 6.0, 10.5], "openInterest": [3000, 6000, 800, 20, 5]})
    return calls, puts


def test_straddle_sd_from_atm_mid():
    c, p = _chain()
    sd, k = ol.straddle_sd(c, p, 100.0)
    assert k == 100.0
    assert abs(sd - 0.06 / ol.MEAN_ABS_PER_SD) < 1e-9


def test_oi_walls_pick_biggest_strikes_each_side():
    c, p = _chain()
    w = ol.oi_walls([(c, p)], 100.0)
    assert (w["call_wall"], w["put_wall"]) == (105.0, 95.0)
    assert [x["price"] for x in ol.wall_levels(w)] == [105.0, 95.0]


def test_day_range_fields_spread_over_sessions():
    opt = {"sd_to_expiry": 0.04, "expiry": "2026-11-20"}  # Wed..Fri = 3 sessions
    one = ol.day_range_fields(opt, 100.0, session_day=date(2026, 11, 18), live_left=None)
    assert abs(one["opt_sd_pct"] - 4 / 3 ** 0.5) < 0.01
    assert one["opt_low80"] < 100 < one["opt_high80"]
    late = ol.day_range_fields(opt, 100.0, session_day=date(2026, 11, 18), live_left=0.25)
    assert late["opt_sd_pct"] < one["opt_sd_pct"]
    assert ol.day_range_fields(None, 100.0, session_day=date(2026, 11, 18), live_left=None) == {}
