import numpy as np
import pandas as pd
import pytest

from research import panel as rp
from research.dsl import RuleError, describe, evaluate, family_key, validate
from research.event_study import car_study, rule_events
from research.features import FeatureCache
from research.screener import screen
from research.tester import backtest, simulate


def _membership(rows):
    m = pd.DataFrame(rows, columns=["ticker", "start_date", "end_date", "sector"])
    m["start_date"] = pd.to_datetime(m["start_date"])
    m["end_date"] = pd.to_datetime(m["end_date"])
    return m


def _panel(n=700, seed=0, members=None):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2015-01-01", periods=n)
    tick = ["AAA", "BBB", "CCC", "SPY"]
    close = pd.DataFrame(100 * np.exp(np.cumsum(rng.normal(0, 0.01, (n, 4)), axis=0)), index=idx, columns=tick)
    frames = {"close": close, "open": close.shift(1).fillna(close), "high": close * 1.01, "low": close * 0.99,
              "volume": pd.DataFrame(1e6, index=idx, columns=tick)}
    m = members if members is not None else _membership([("AAA", "2010-01-01", None, "Tech"), ("BBB", "2010-01-01", None, "Energy"),
                                ("CCC", "2010-01-01", None, "Tech")])
    return rp.from_frames({k: v.astype("float32") for k, v in frames.items()}, m, ("SPY",), {"as_of": str(idx[-1].date())})


def test_validate_rejects_bad_rules():
    for bad in ({"all": []}, {"field": "nope", "op": ">", "value": 1}, {"field": "rsi14", "op": "~", "value": 1},
                {"field": "rsi14", "op": ">", "value": "x"}, {"field": "trend_template", "op": "top_pct", "value": 10},
                {"all": [{"field": "rsi14", "op": ">", "value": 1}] * 13}):
        with pytest.raises(RuleError):
            validate(bad)


def test_family_key_ignores_thresholds_and_describe():
    a = {"all": [{"field": "rsi14", "op": "<", "value": 30}, {"field": "dist_sma200", "op": ">", "value": 0}]}
    b = {"all": [{"field": "dist_sma200", "op": ">", "value": 5}, {"field": "rsi14", "op": "<", "value": 25}]}
    assert family_key(a) == family_key(b)
    assert describe(a) == "RSI (14) < 30 AND vs 200-day average > 0"


def test_features_use_only_past_data():
    p = _panel()
    fc = FeatureCache(p)
    full = fc.get("rsi14").iloc[400]
    q = _panel()
    cut = rp.Panel(**{f: getattr(q, f).iloc[:401] for f in rp.FIELDS}, members=q.members.iloc[:401], sectors=q.sectors, etfs=q.etfs)
    assert np.allclose(FeatureCache(cut).get("rsi14").iloc[400].values, full.values, equal_nan=True)


def test_screen_respects_membership_and_sector():
    m = _membership([("AAA", "2010-01-01", None, "Tech"), ("BBB", "2010-01-01", "2016-01-01", "Energy"), ("CCC", "2010-01-01", None, "Tech")])
    fc = FeatureCache(_panel(members=m))
    out = screen(fc, {"field": "price", "op": ">", "value": 0})
    assert {r["ticker"] for r in out["rows"]} == {"AAA", "CCC"}
    out = screen(fc, {"all": [{"field": "price", "op": ">", "value": 0}, {"field": "sector", "op": "in", "value": ["Energy"]}]})
    assert out["n_matches"] == 0
    assert "SPY" in {r["ticker"] for r in screen(fc, {"field": "price", "op": ">", "value": 0}, include_etfs=True)["rows"]}


def test_simulate_enters_next_open_and_handles_stop_gap_target():
    T = 10
    O = np.full((T, 1), 100.0); H = O * 1.01; L = O * 0.99; C = O.copy()
    sig = np.zeros((T, 1), bool); sig[2, 0] = True
    O[5, 0], H[5, 0], L[5, 0], C[5, 0] = 90, 91, 89, 90
    tr = simulate(O, H, L, C, sig, hold=6, stop_pct=5, target_pct=None, start_i=0, end_i=T - 1)
    j, si, e, x, px, xp, reason = tr[0]
    assert (si, e, px) == (2, 3, 100.0) and (x, xp, reason) == (5, 90.0, "stop_gap")
    H[4, 0] = 112
    tr = simulate(O, H, L, C, sig, hold=6, stop_pct=5, target_pct=10, start_i=0, end_i=T - 1)
    assert tr[0][6] == "target" and tr[0][5] == pytest.approx(110.0)
    L[4, 0] = 90
    assert simulate(O, H, L, C, sig, 6, 5, 10, 0, T - 1)[0][6] == "stop"


def test_simulate_one_position_per_ticker_and_time_exit():
    T = 30
    O = np.full((T, 1), 100.0); H = O + 1; L = O - 1; C = O.copy()
    sig = np.ones((T, 1), bool)
    tr = simulate(O, H, L, C, sig, hold=5, stop_pct=None, target_pct=None, start_i=0, end_i=T - 1)
    assert all(t[6] in ("time", "open") for t in tr)
    assert all(b[1] > a[3] for a, b in zip(tr, tr[1:]))


def test_backtest_costs_split_and_promotion():
    fc = FeatureCache(_panel(1200))
    rule = {"field": "ret_5d", "op": "<", "value": -2}
    a = backtest(fc, rule, hold_days=5, cost_bps=0, split_date="2018-01-01")
    b = backtest(fc, rule, hold_days=5, cost_bps=50, split_date="2018-01-01")
    assert a["all"]["n"] == b["all"]["n"] > 30
    assert b["all"]["mean"] == pytest.approx(a["all"]["mean"] - 0.5, abs=0.02)
    assert a["in_sample"]["n"] + a["out_of_sample"]["n"] == a["all"]["n"]
    assert b["promotion"]["passes"] is False and b["promotion"]["sample"] == "out_of_sample"
    assert len(b["curve"]["dates"]) == len(b["curve"]["strategy"]) == len(b["curve"]["spy"])


def test_clip_to_membership_drops_reused_symbol_bars():
    idx = pd.bdate_range("2010-01-01", periods=2000)
    c = pd.DataFrame({"OLD": 10.0, "SPY": 100.0}, index=idx)
    frames = {f: c.copy() for f in rp.FIELDS}
    m = _membership([("OLD", "2011-06-01", "2012-01-03", "Tech")])
    out = rp.clip_to_membership(frames, m, ("SPY",))
    s = out["close"]["OLD"].dropna()
    assert s.index.min() >= pd.Timestamp("2011-06-01") - pd.Timedelta(days=rp.PRE_MEMBER_DAYS)
    assert s.index.max() <= pd.Timestamp("2012-01-03") + pd.Timedelta(days=rp.POST_MEMBER_DAYS)
    assert out["close"]["SPY"].notna().all()


def test_reused_symbol_suspects():
    idx = pd.bdate_range("2020-01-01", periods=60)
    jumpy = np.where(np.arange(60) % 2, 1.0, 2.0)
    c = pd.DataFrame({"BAD": jumpy, "OK": np.linspace(10, 12, 60)}, index=idx)
    assert rp.reused_symbol_suspects(c) == ["BAD"]


def test_event_study_day0_after_signal_and_clustered():
    fc = FeatureCache(_panel(900))
    ev = rule_events(fc, {"field": "ret_1d", "op": "<", "value": -1.5})
    assert ev and all(len(e) == 3 for e in ev)
    out = car_study(fc, ev, pre=3, post=5)
    assert out["n_events"] > 10 and out["n_dates"] <= out["n_events"]
    assert len(out["mean"]) == len(out["days"]) == 9
    assert out["from_day_minus1"][0]["day"] == 0
