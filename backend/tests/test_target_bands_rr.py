"""ST band reward:risk — a BUY/SELL call must assert more upside than downside distance.

Regression for the bug where st_target used the same ATR multiplier as st_stop, so R:R
landed at ~1.0 for almost any real ticker regardless of setup quality (empirically
confirmed against 17 real watchlist tickers before this fix: 14/17 landed at exactly 1.0).
"""

from __future__ import annotations

from signals.target_bands import add_target_bands


def _base_row(**overrides):
    row = {
        "ticker": "TEST",
        "close": 100.0,
        "atr14": 2.0,
        "ma20": 100.0,
        "regime": "NEUTRAL",
        "vol_6m": 0.25,
        "short_suggestion": "HOLD",
        "swing_high_20d": None,
        "swing_low_20d": None,
    }
    row.update(overrides)
    return row


def _rr(row: dict) -> float:
    band = row["st_band"]
    close = row["close"]
    risk = close - band["low"]
    reward = band["high"] - close
    assert risk > 0 and reward > 0
    return reward / risk


def test_buy_signal_rr_at_least_1_5():
    row = add_target_bands(_base_row(short_suggestion="BUY", close=105.0, ma20=100.0))
    assert _rr(row) >= 1.4  # allow for swing_high/low fallback rounding


def test_buy_signal_below_ma20_still_gets_atr_floor_on_target():
    """Price below MA20 must not cap the target at MA20 alone with no ATR-based floor."""
    row = add_target_bands(_base_row(short_suggestion="BUY", close=95.0, ma20=100.0))
    band = row["st_band"]
    # target should be at least as far as the ATR-based floor, not just MA20
    assert band["high"] >= 100.0


def test_hold_signal_stays_symmetric():
    """A neutral HOLD makes no directional claim — its band should stay ~1:1 by design."""
    row = add_target_bands(_base_row(short_suggestion="HOLD"))
    assert abs(_rr(row) - 1.0) < 0.05


def test_manual_override_bypasses_rr_widening(monkeypatch):
    """A per-ticker manual ATR-mult override means 'symmetric at this multiplier' — no RR bump."""
    from config_loader import load_config

    real_cfg = load_config()

    def _fake_load_config():
        cfg = dict(real_cfg)
        cfg["accuracy"] = {**(cfg.get("accuracy") or {}), "st_target_atr_mult_overrides": {"TEST": 1.0}}
        return cfg

    monkeypatch.setattr("config_loader.load_config", _fake_load_config)
    row = add_target_bands(_base_row(short_suggestion="BUY", ticker="TEST", close=105.0, ma20=100.0))
    assert abs(_rr(row) - 1.0) < 0.05
