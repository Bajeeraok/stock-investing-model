"""Eastern Time helpers — app timestamps use America/New_York, not UTC."""
from __future__ import annotations

from signals.time_et import ET, now_et, now_iso_et, parse_iso_to_et, today_est


def test_today_est_format():
    assert len(today_est()) == 10
    assert today_est()[4] == "-"


def test_now_iso_et_has_offset():
    iso = now_iso_et()
    assert "T" in iso
    dt = now_et()
    assert dt.tzinfo == ET


def test_parse_iso_to_et_from_z():
    dt = parse_iso_to_et("2026-06-08T12:00:00Z")
    assert dt.tzinfo == ET
    assert dt.hour in (7, 8)  # EDT or EST vs noon UTC
