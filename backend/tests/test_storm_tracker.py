from signals.storm_tracker import build, spells


def test_spells_end_after_five_closes_above():
    b = [False] * 3 + [True] * 6 + [False, True] + [False] * 6 + [True] * 4
    sp = spells(b)
    assert sp[0] == (3, 10) and sp[-1] == (17, 20)


def test_build_reports_open_spell_against_past():
    import math
    close = [100 * math.exp(0.001 * i + 0.08 * math.sin(i / 15)) for i in range(800)]
    dates = [f"d{i}" for i in range(800)]
    r = build(close, dates, [20.0] * 800, [21.0] * 800)
    assert r["past"]["n"] > 5 and 0 <= r["past"]["over_by_pct"][20] <= 100
    assert len(r["recent_spells"]) <= 12
    if r.get("spell"):
        assert r["spell"]["days"] >= 1 and 0 <= r["spell"]["past_ended_by_now_pct"] <= 100
