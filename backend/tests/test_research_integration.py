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


def test_rule_alerts_only_strong_rules_on_turn_on_day(env, monkeypatch):
    import research.alerts as ra
    from alerts.events import AlertEventStore

    stored = []
    monkeypatch.setattr(AlertEventStore, "append_events", lambda self, evs: stored.extend(evs))
    fc = FeatureCache(_panel())
    idx = fc.p.close.index
    last, prev = float(fc.p.close["AAA"].iloc[-1]), float(fc.p.close["AAA"].iloc[-2])
    thr = (last + prev) / 2
    turns_on = {"field": "price", "op": ">" if last > prev else "<", "value": round(thr, 4)}
    env += [_run("strong", turns_on, True), _run("weak", {**turns_on, "value": round(thr, 4) + 1e-5}, False), _run("always", RULE_ON, True, ts=2)]
    rows = {"as_of": str(idx[-1].date()), "modes": {"swing": {"AAA": {
        "price": last, "status": None, "gates_failing": ["Trend weather"], "band_low": 1.0, "band_high": 2.0,
        "band_gap_pct": 5.0, "stop": 0.5, "target": 3.0}}}}
    assert ra.publish_rule_alerts(fc=fc, rows={**rows, "as_of": "1999-01-01"}, tickers=["AAA"]) == 0
    assert ra.publish_rule_alerts(fc=fc, rows=rows, tickers=["AAA", "BBB"]) == 1
    ev = stored[0]
    assert ev.ticker == "AAA" and ev.payload["run_id"] == "strong" and not ev.payload["gates_clear"]
    assert "gates blocked (Trend weather)" in ev.message and "above band" in ev.message
    assert ra.publish_rule_alerts(fc=fc, rows=rows, tickers=["AAA"]) == 0
    assert ra.publish_rule_alerts(fc=fc, rows=None, tickers=["AAA"]) == 0


def test_rule_alerts_skip_without_panel(env):
    import research.alerts as ra

    assert ra.publish_rule_alerts(rows={"as_of": "2017-09-06", "modes": {}}, tickers=["AAA"]) == 0


def test_deleted_run_hidden_but_still_counts_as_try(tmp_path, monkeypatch):
    import json as _json
    import research.panel as rp
    import research.service as svc

    monkeypatch.setattr(rp, "panel_dir", lambda: tmp_path)
    rows = [{"id": "a", "family": "f", "hash": "h1", "rule": {"field": "rsi14", "op": "<", "value": 30}},
            {"id": "b", "family": "f", "hash": "h2", "rule": {"field": "rsi14", "op": "<", "value": 25}}]
    (tmp_path / "runs.jsonl").write_text("\n".join(_json.dumps(r) for r in rows))
    assert svc.delete_run("a") and not svc.delete_run("zzz")
    assert [r["id"] for r in svc.read_runs()] == ["b"]
    assert len(svc.read_runs(include_deleted=True)) == 2
    assert svc.family_trials("f")[0] == 2
    from research.integration import saved_rules
    assert [r["id"] for r in saved_rules()] == ["b"]
