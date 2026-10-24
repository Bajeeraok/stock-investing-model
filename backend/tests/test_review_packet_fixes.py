"""Regressions for the Oct 2026 review-packet findings."""
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

from signals.retail_action_payload import _ml_gate_detail, derive_action_title
from signals.swing_classifier import SwingSetupType, build_swing_exit_plan
from signals.target_bands import _cap_band_width_for_display


def test_missing_ml_is_unscored_not_zero():
    detail, visual, ok = _ml_gate_detail(None)
    assert visual == "unscored" and ok is True and "0%" not in detail
    assert _ml_gate_detail(10.0)[2] is False  # a real low probability still blocks


def test_lt_band_cap_centers_on_fair_value_not_tail():
    lo, hi, capped = _cap_band_width_for_display(123.0, 700.0, spot=334.0, band_key="lt", anchor=508.0)
    assert capped and lo <= 508.0 <= hi and lo > 334.0 * 0.5


def test_blocked_buy_is_not_tactical_entry():
    assert derive_action_title("BUY", gate_cleared=False)[0] != "TACTICAL ENTRY"
    assert derive_action_title("BUY", gate_cleared=True)[0] == "TACTICAL ENTRY"


def test_oversold_bounce_stop_capped():
    p = build_swing_exit_plan(SwingSetupType.OVERSOLD_BOUNCE, {"price": 535.0, "atr": 18.0, "recent_low": 190.0})
    assert p["hard_stop"] >= 535.0 * 0.92 - 0.01 and p["target_1"] < 650 and p["stop_capped"]


def test_yfinance_past_earnings_date_is_not_negative_days():
    import signals.providers as prov

    past = date.today() - timedelta(days=7)
    t = MagicMock()
    t.calendar = {"Earnings Date": [past]}
    with patch.object(prov, "yf") as yf:
        yf.Ticker.return_value = t
        assert prov._get_earnings_yfinance("JNJ") is None
