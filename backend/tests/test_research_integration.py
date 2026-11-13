import pytest

import research.integration as ri
from research import panel as rp
from research import service as rs
from research.features import FeatureCache
from research.screener import screen
from signals.best_setups import build_report
from tests.test_best_setups import _detail
from tests.test_research_tools import _membership, _panel

RULE_ON = {"field": "price", "op": ">", "value": 0}
RULE_OFF = {"field": "price", "op": "<", "value": 0}


def _run(rid, rule, passes, ts=1.0):
    return {"id": rid, "ts": ts, "rule": rule, "rule_text": rid, "params": {"hold_days": 20},
            "oos": {"n": 40, "mean": 1.2, "win_rate": 55}, "promotion": {"passes": passes, "t_stat": 3.4}}


@pytest.fixture
def env(tmp_path, monkeypatch):
    runs = []
    monkeypatch.setattr(rp, "panel_dir", lambda: tmp_path)
    monkeypatch.setattr(rs, "read_runs", lambda limit=None: list(runs))
    ri._hits_cache.clear()
    return runs


def test_screen_restricted_to_our_tickers():
    m = _membership([("AAA", "2010-01-01", None, "Tech"), ("BBB", "2010-01-01", "2016-01-01", "Energy"),
                     ("CCC", "2010-01-01", None, "Tech")])
    fc = FeatureCache(_panel(members=m))
    full = screen(fc, RULE_ON)
    assert {r["ticker"] for r in full["rows"]} == {"AAA", "CCC"} and full["universe"] == "sp500"
    ours = screen(fc, RULE_ON, only=["bbb", "CCC", "ZZZ"])
    assert {r["ticker"] for r in ours["rows"]} == {"BBB", "CCC"}
    assert ours["universe"] == "ours" and ours["universe_n"] == 2 and ours["universe_requested"] == 3


def test_only_passing_runs_can_be_approved(env):
    env += [_run("bad", RULE_ON, False), _run("good", RULE_ON, True)]
    with pytest.raises(ValueError):
        ri.approve("bad")
    with pytest.raises(KeyError):
        ri.approve("missing")
    ri.approve("good")
    assert set(ri.load_approved()) == {"good"}
    assert ri.unapprove("good") and ri.load_approved() == {}


def test_badges_show_rules_on_today_with_record(env):
    fc = FeatureCache(_panel())
    env += [_run("on", RULE_ON, False), _run("off", RULE_OFF, False)]
    hits = ri.rule_hits(["AAA"], fc=fc)
    assert list(hits) == ["AAA"]
    b = hits["AAA"][0]
    assert b["run_id"] == "on" and not b["approved"] and b["oos_n"] == 40 and b["t_stat"] == 3.4


def test_unapproved_rules_do_not_reorder(env):
    fc = FeatureCache(_panel())
    env.append(_run("on", RULE_ON, True))
    rep = build_report(previous={}, details=[_detail("AAA", prob=70), _detail("BBB", prob=55)], boosted=set())
    rep = ri.annotate_best_setups(rep, fc=fc)
    picks = rep["modes"]["swing"]["picks"]
    assert [r["ticker"] for r in picks] == ["AAA", "BBB"]
    assert picks[0]["research"] and not picks[0]["research_boost"]


def test_approved_rule_moves_pick_up_without_changing_gates(env):
    fc = FeatureCache(_panel())
    bbb_only = {"all": [RULE_ON, {"field": "sector", "op": "in", "value": ["Energy"]}]}
    env.append(_run("good", bbb_only, True))
    ri.approve("good")
    details = [_detail("AAA", prob=70), _detail("BBB", prob=55), _detail("CCC", prob=70, entry_mode="hard_lock")]
    rep = build_report(previous={}, details=details, boosted=ri.approved_hit_tickers(fc=fc))
    rep = ri.annotate_best_setups(rep, fc=fc)
    sw = rep["modes"]["swing"]
    assert [r["ticker"] for r in sw["picks"]] == ["BBB", "AAA"]
    assert sw["picks"][0]["research_boost"] and not sw["picks"][1]["research_boost"]
    assert [r["ticker"] for r in sw["next_up"]] == ["CCC"] and not sw["next_up"][0]["qualified"]


def test_missing_panel_leaves_report_unchanged(env, monkeypatch):
    monkeypatch.setattr(ri, "get_fc", lambda: None)
    rep = build_report(previous={}, details=[_detail("AAA")], boosted=None)
    assert ri.rule_hits() == {}
    out = ri.annotate_best_setups(rep)
    assert out["modes"]["swing"]["picks"][0]["research"] == []
    assert ri.annotate_best_setups(None) is None
