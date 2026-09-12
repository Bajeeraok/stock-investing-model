"""Regression: a cached Layer-3 narrative claiming spot is "above the buy zone" must not
survive a real crossing into the zone. Reported live on MSFT — entry_band.hi=$495.63, spot
drifted from $496.10 (above) down to $495.63 (inside), but the why-explainer still said
"currently above its buy zone... wait for a pullback into $490.67-$495.63" because
decision_hash()'s spot_bucket (whole dollars above $250) doesn't distinguish $496.10 from
$495.63 — both round to 496, so the stale narrative's cache key never changed.
"""

from __future__ import annotations

from signals.narrative_waterfall import example_packet_amzn


def test_zone_position_above_vs_inside():
    p = example_packet_amzn()
    assert p.entry_band is not None
    hi = p.entry_band.hi  # 257.52

    p.spot = hi + 0.08  # 257.60 — clearly above
    assert p.zone_position() == "above"

    p.spot = hi  # 257.52 — exactly at the ceiling, inclusive == inside
    assert p.zone_position() == "inside"


def test_decision_hash_changes_when_zone_position_flips_within_same_spot_bucket():
    p = example_packet_amzn()
    hi = p.entry_band.hi

    p.spot = hi + 0.08  # 257.60 -> spot_bucket round() = 258, zone = above
    above_hash = p.decision_hash()

    p.spot = hi  # 257.52 -> spot_bucket round() = 258 too (same bucket!), zone = inside
    assert round(hi + 0.08) == round(hi), "test setup must keep both spots in one bucket"
    inside_hash = p.decision_hash()

    assert above_hash != inside_hash, (
        "decision_hash must change when zone_position flips even though spot_bucket doesn't — "
        "otherwise a stale 'above the buy zone' narrative can survive a real crossing"
    )
