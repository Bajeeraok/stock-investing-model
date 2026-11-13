from signals.fv_stability import stabilize
from signals.investor_rules import _hit_story_change

EPS = (7.91, 9.29)


def test_first_value_accepted():
    fv, st, note = stabilize(None, 233.7, EPS, "2026-11-10")
    assert fv == 233.7 and note is None and st["fv"] == 233.7


def test_small_move_accepted():
    _, st, _ = stabilize(None, 233.7, EPS, "2026-11-10")
    fv, _, note = stabilize(st, 245.0, EPS, "2026-11-11")
    assert fv == 245.0 and note is None


def test_jump_without_eps_change_held_then_confirmed():
    _, st, _ = stabilize(None, 233.7, EPS, "2026-11-11")
    fv, st, note = stabilize(st, 169.5, EPS, "2026-11-12")
    assert fv == 233.7 and "held" in note
    fv, st2, note = stabilize(st, 169.5, EPS, "2026-11-12")  # same day repeat does not confirm
    assert fv == 233.7 and note
    fv, st3, note = stabilize(st2, 170.0, EPS, "2026-11-13")  # repeats next day -> accept
    assert fv == 170.0 and note is None and "pending" not in st3


def test_flap_back_keeps_held_value():
    _, st, _ = stabilize(None, 233.7, EPS, "2026-11-11")
    _, st, _ = stabilize(st, 169.5, EPS, "2026-11-12")
    fv, _, note = stabilize(st, 233.6, EPS, "2026-11-13")
    assert fv == 233.6 and note is None


def test_jump_with_eps_change_accepted():
    _, st, _ = stabilize(None, 233.7, EPS, "2026-11-11")
    fv, _, note = stabilize(st, 300.0, (9.5, 11.0), "2026-11-12")
    assert fv == 300.0 and note is None


def test_horizon_shift_is_not_lynch_story_change():
    assert _hit_story_change({"story_change": "HORIZON SHIFT: SHORT, MEDIUM playbook changed",
                              "story_change_source": "horizon"}) is None
    assert _hit_story_change({"story_change": "Plan rebuilt", "story_change_source": "horizon"}) is None
    assert _hit_story_change({"story_change": "Guidance cut: FY revenue lowered",
                              "story_change_source": "fundamental"}) == "Guidance cut: FY revenue lowered"
    assert _hit_story_change({}) is None
