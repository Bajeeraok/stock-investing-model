"""
Regression coverage for a float-precision boundary bug: comparing a raw, full-precision
current_price against cent-rounded band edges could put spot a few thousandths of a cent
*above* its own band ceiling when that ceiling was itself defined as "clamped to spot" (i.e.
equal to current price, just rounded). Confirmed live on SNDK: current_price
1712.8900146484375 vs a short-term band ceiling of 1712.89 (band_high computed as round(spot,
2)) — the unrounded comparison said spot was outside its own band, which flipped the ticker
detail's "Today" roadmap row from the correct short-term band ($1695.76-$1712.89, matching the
SWING tab) to the medium-term band ($1508.68-$1584.88, ~12% lower) for a ticker that was, in
reality, sitting right at the top of its short-term range.

Two call sites shared this bug and are both covered here:
  - signals/swing_setup.py::_inside_band (feeds the SWING tab's own "inside_entry_band" flag)
  - api/ticker_detail.py's inline in_st_band/in_mt_band checks (feeds which band the Buy
    Roadmap's Today/Days/Week rows show)
"""
from __future__ import annotations

from signals.swing_setup import _inside_band


def test_inside_band_handles_raw_price_fractionally_above_rounded_ceiling():
    # The exact live SNDK values: ceiling was round(current_price, 2); comparing the raw,
    # unrounded current_price against it used to read as "outside" by ~0.0000146.
    assert _inside_band(1712.8900146484375, 1695.76, 1712.89) is True


def test_inside_band_still_false_when_meaningfully_above():
    assert _inside_band(1750.00, 1695.76, 1712.89) is False


def test_inside_band_still_false_when_meaningfully_below():
    assert _inside_band(1600.00, 1695.76, 1712.89) is False


def test_inside_band_true_at_exact_low_edge():
    assert _inside_band(1695.76, 1695.76, 1712.89) is True


def test_inside_band_none_inputs_return_false():
    assert _inside_band(None, 1695.76, 1712.89) is False
    assert _inside_band(1700.0, None, 1712.89) is False
    assert _inside_band(1700.0, 1695.76, None) is False


def test_inside_band_handles_swapped_lo_hi():
    assert _inside_band(1700.0, 1712.89, 1695.76) is True
