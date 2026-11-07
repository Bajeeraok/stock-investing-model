import pandas as pd

from signals.best_setups import build_report, pick_outcome, setup_row


def _detail(ticker="AAA", price=100.0, entry_mode="full_go", rr=2.5, prob=60.0, band=(96.0, 99.0),
            target=120.0, stop=90.0, setup_status="ok"):
    return {
        "ticker": ticker,
        "current_price": price,
        "investor_summary": {
            "retail_action": {"entry_mode": entry_mode,
                              "display_by_mode": {"swing": {"gates_passed": 2, "gates_total": 4},
                                                  "owner": {"gates_passed": 2, "gates_total": 4}}},
            "horizons": {
                "medium": {"entry_zone": {"low": band[0], "high": band[1], "levels": [
                    {"role": "entry", "price": band[1], "target_first_pct": 40, "stop_first_pct": 45}]},
                    "target": target, "stop_loss": stop, "risk_reward_from_entry": rr,
                    "ml_prob": prob, "ml_scored": True, "setup_status": setup_status, "hist_prob": 50},
                "long": {"entry_zone": {"low": 80.0, "high": 85.0}, "target": 130.0, "stop_loss": 70.0,
                         "risk_reward_from_entry": 3.0, "ml_prob": 50.0, "ml_scored": True},
            },
        },
    }


def test_qualified_swing_row_and_edge():
    r = setup_row(_detail(), "swing")
    assert r["qualified"] and r["status"] == "Can add"
    mid = 97.5
    tgt, stp = (120 - mid) / mid * 100, (mid - 90) / mid * 100
    assert abs(r["edge_pct"] - round(0.40 * tgt - 0.45 * stp, 2)) < 0.01
    assert r["target_first_pct"] == 40


def test_blockers_hard_lock_low_rr_and_far_band():
    r = setup_row(_detail(entry_mode="hard_lock", rr=1.6), "swing")
    assert not r["qualified"]
    assert "entry gates" in r["blockers"] and "R:R under 2.0" in r["blockers"]
    owner = setup_row(_detail(), "owner")  # price 100 vs band top 85 → far above band
    assert "price above band" in owner["blockers"]


def test_low_chance_blocks_and_history_caps_model():
    r = setup_row(_detail(prob=30), "swing", model_ok=True)
    assert r["blockers"] == ["chance under 40%"]
    r = setup_row(_detail(prob=30), "swing")  # unproven model is shown but ignored
    assert r["qualified"] and r["chance"] == 50 and r["model_proven"] is False
    d = _detail(prob=95)
    d["investor_summary"]["horizons"]["medium"].update(hist_prob=45, hist_prob_similar=42)
    r = setup_row(d, "swing", model_ok=True)
    assert r["chance"] == 42 and r["hist_basis"] == "similar" and r["odds_gap"] and r["qualified"]


def test_new_flag_vs_previous_day():
    prev = {"as_of": "2026-01-01", "modes": {"swing": {"picks": [{"ticker": "AAA"}]}}}
    rep = build_report([_detail("AAA"), _detail("BBB")], previous=prev)
    flags = {r["ticker"]: r["new"] for r in rep["modes"]["swing"]["picks"]}
    assert flags == {"AAA": False, "BBB": True} and rep["new_count"] >= 1


def test_ranking_and_next_up():
    rep = build_report(previous={}, details=[
        _detail("AAA", prob=70),
        _detail("BBB", prob=55),
        _detail("CCC", prob=70, entry_mode="hard_lock"),
        {"ticker": "BTC-USD", "current_price": 1.0},
    ])
    sw = rep["modes"]["swing"]
    assert [r["ticker"] for r in sw["picks"]] == ["AAA", "BBB"]
    assert [r["ticker"] for r in sw["next_up"]] == ["CCC"]


def test_dip_watch_is_weather_only_and_not_a_pick():
    def locked(t, failing):
        d = _detail(t, entry_mode="hard_lock")
        d["investor_summary"]["retail_action"]["gates_by_mode"] = {"swing": [
            {"id": g, "pass": g not in failing} for g in ("valuation", "regime", "momentum", "ml")]}
        return d

    rep = build_report(previous={}, details=[locked("DIP", {"regime"}), locked("VAL", {"valuation"}),
                                             locked("TWO", {"regime", "ml"})])
    sw = rep["modes"]["swing"]
    assert [r["ticker"] for r in sw["dip_watch"]] == ["DIP"]
    assert sw["picks"] == [] and "DIP" not in [r["ticker"] for r in sw["next_up"]]


def test_pick_outcome_target_first():
    idx = pd.to_datetime(["2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07"])
    bars = pd.DataFrame({"close": [100, 104, 112, 121], "high": [101, 105, 113, 122],
                         "low": [99, 102, 110, 118]}, index=idx)
    pk = {"price": 100.0, "target": 120.0, "stop": 92.0}
    oc = pick_outcome(pk, "2026-01-02", bars, 63)
    assert oc["result"] == "target" and oc["return_pct"] == 20.0
    oc2 = pick_outcome({"price": 100.0, "target": 130.0, "stop": 103.0}, "2026-01-02", bars, 63)
    assert oc2["result"] == "stop"


def test_forward_gain_odds_and_model_check():
    import numpy as np

    from signals.level_touch_odds import forward_gain_odds
    from signals.model_odds_check import outcomes_for_ticker, score_calls

    closes = np.array([100.0 * (1.001 ** i) for i in range(400)])
    pct, n = forward_gain_odds(closes, 5.0, 60)
    assert pct == 100 and n == 340
    assert forward_gain_odds(closes, 10.0, 60)[0] == 0
    idx = pd.bdate_range("2026-01-01", periods=80)
    bars = pd.DataFrame({"close": [100.0] * 70 + [120.0] * 10}, index=idx)
    oc = outcomes_for_ticker([(idx[0].date().isoformat(), 90.0), (idx[30].date().isoformat(), 85.0)], bars, 60, 10.0)
    assert oc == [(90.0, False)]
    sc = score_calls(oc + [(85.0, True)])
    assert sc["buckets"][0]["came_true_pct"] == 50.0


def test_model_verdict_and_trust_gate():
    from signals.model_odds_check import model_trusted, score_calls, verdict

    assert verdict(score_calls([(90.0, True)] * 10)) == "unproven"
    flat = [(80.0, i % 2 == 0) for i in range(300)]  # says 80%, comes true 50%
    assert verdict(score_calls(flat)) == "no_edge"
    good = [(80.0, i % 5 != 0) for i in range(200)] + [(20.0, i % 5 == 0) for i in range(200)]
    sc = score_calls(good)
    assert sc["skill_pct"] > 0 and verdict(sc) == "proven"
    assert model_trusted("medium", {"horizons": {"medium": sc}})
    assert not model_trusted("long", {"horizons": {"medium": sc}})


def test_odds_model_version_boundary():
    from signals.model_version import odds_model_is_current

    assert odds_model_is_current("2026.11.1") and odds_model_is_current("2026.11.10")
    assert odds_model_is_current("2027.1.1")
    assert not odds_model_is_current("2026.10.2")
    assert not odds_model_is_current("legacy") and not odds_model_is_current(None)


def test_model_check_splits_calls_by_odds_model(tmp_path, monkeypatch):
    import sqlite3

    from signals.model_odds_check import build_model_check, model_trusted, score_calls

    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    idx = pd.bdate_range("2026-01-01", periods=80)
    bars = pd.DataFrame({"close": [100.0] * 40 + [120.0] * 40}, index=idx)
    with sqlite3.connect(tmp_path / "signal_audit.db") as conn:
        conn.execute("CREATE TABLE signal_events (ticker TEXT, signal_date TEXT, ml_short_prob REAL, "
                     "ml_medium_prob REAL, ml_long_prob REAL, model_version TEXT, source TEXT)")
        rows = [("AAA", idx[0].date().isoformat(), 0.6, None, None, "2026.10.2", "live"),
                ("AAA", idx[1].date().isoformat(), 0.7, None, None, None, "live"),
                ("AAA", idx[30].date().isoformat(), 0.4, None, None, "2026.11.1", "live"),
                ("AAA", idx[75].date().isoformat(), 0.3, 0.5, None, "2026.11.3", "live")]
        conn.executemany("INSERT INTO signal_events VALUES (?,?,?,?,?,?,?)", rows)
    rep = build_model_check(fetch=lambda t, period: bars)
    sm = rep["by_model"]["short"]
    assert sm["previous"]["n"] == 2 and sm["current"]["n"] == 1
    assert sm["current_logged"] == 2 and sm["current_first_date"] == idx[30].date().isoformat()
    assert rep["horizons"]["short"]["n"] == 3
    md = rep["by_model"]["medium"]
    assert md["current"] is None and md["previous"] is None and md["current_logged"] == 1

    good = [(80.0, i % 5 != 0) for i in range(200)] + [(20.0, i % 5 == 0) for i in range(200)]
    proven = score_calls(good)
    assert model_trusted("short", {"horizons": {"short": proven}, "by_model": {"short": {"current": None, "previous": proven}}}) is False
    assert model_trusted("short", {"horizons": {"short": None}, "by_model": {"short": {"current": proven}}})


def test_model_check_short_splits_forward_records_by_odds_model():
    from signals.forward_tracking import build_model_check_short

    def rec(v, p, ret):
        return {"ticker": "AAA", "horizon_days": 20, "forward_status": "complete", "model_version": v,
                "ml_short_prob": p, "actual_return_pct": ret}

    out = build_model_check_short([rec("2026.10.2", 0.6, 1.0), rec(None, 0.7, 6.0), rec("2026.11.2", 0.3, 7.0)])
    assert out["odds"]["n"] == 3
    assert out["odds_by_model"]["previous"]["n"] == 2 and out["odds_by_model"]["current"]["n"] == 1
    assert out["odds_model_since"] == "2026.11.1"
