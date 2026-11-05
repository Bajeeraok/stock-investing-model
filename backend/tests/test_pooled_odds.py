import json

import numpy as np
import pandas as pd
import pytest

lgb = pytest.importorskip("lightgbm")

from signals import pooled_odds as po  # noqa: E402
from signals.ml_models import predict_all_horizons  # noqa: E402
from signals.probability_calibration import apply_calibration_to_ml_horizons  # noqa: E402


def _ohlcv(n=800, seed=0, drift=0.0005):
    rng = np.random.default_rng(seed)
    c = 100 * np.exp(np.cumsum(rng.normal(drift, 0.02, n)))
    idx = pd.bdate_range("2020-01-01", periods=n)
    return pd.DataFrame({"close": c, "high": c * 1.01, "low": c * 0.99, "volume": 1e6}, index=idx)


@pytest.fixture(autouse=True)
def _no_network_history(monkeypatch, request):
    if request.node.name != "test_long_close_uses_history_since_2000_up_to_the_frame_end":
        monkeypatch.setattr(po, "_long_close", lambda ticker, close: close)


def test_long_close_uses_history_since_2000_up_to_the_frame_end(monkeypatch):
    full = pd.Series(1.0, index=pd.bdate_range("1995-01-02", "2026-10-23"))
    frame = full.loc["2024-10-01":"2026-06-30"]
    import signals.fetcher as fetcher
    monkeypatch.setattr(fetcher, "fetch_ohlcv_safe", lambda t, period: full)
    out = po._long_close("AAPL", frame)
    assert out.index[0] >= po.HIST_START and out.index[0] < pd.Timestamp("2000-01-10")
    assert out.index[-1] == frame.index[-1]
    monkeypatch.setattr(fetcher, "fetch_ohlcv_safe", lambda t, period: None)
    assert po._long_close("AAPL", frame) is frame


def test_eligibility_keeps_crypto_and_defensive_on_per_ticker_path():
    assert po.pooled_eligible("COIN") and po.pooled_eligible("MSTR") and po.pooled_eligible("AAPL")
    for t in ("BTC-USD", "ETH-USD", "GLD", "TLT", ""):
        assert not po.pooled_eligible(t)


def test_features_do_not_use_future_bars():
    df, spy = _ohlcv(seed=1), _ohlcv(seed=2)
    full = po.ticker_features(df, po.market_features(spy["close"]), "AAPL")
    cut = po.ticker_features(df.iloc[:600], po.market_features(spy["close"].iloc[:600]), "AAPL")
    cols = [c for c in cut.columns if c != "regime_is_high_vol"]
    pd.testing.assert_frame_equal(full.loc[cut.index[-50:], cols], cut.iloc[-50:][cols], check_dtype=False)


def test_history_rate_only_counts_known_outcomes():
    close = pd.Series(np.linspace(100, 200, 400), index=pd.bdate_range("2020-01-01", periods=400))
    s = po.history_rate_series(close, 20, 0.05)
    assert s.iloc[:119].isna().all() and s.iloc[119:].notna().all()
    y = po.forward_label(close, 20, 0.05)
    i = 300
    assert s.iloc[i] == pytest.approx(y.iloc[: i - 20 + 1].mean())
    assert po.history_rate(close.iloc[:50], 20, 0.05) is None


def _artifact(tmp_path, weight=0.3):
    df, spy = _ohlcv(seed=3), _ohlcv(seed=4)
    f = po.ticker_features(df, po.market_features(spy["close"]), "AAPL").copy()
    f["gain"] = 0.05
    f["y"] = po.forward_label(df["close"], 20, 0.05).reindex(f.index)
    d = f.dropna()
    feats = [c for c in d.columns if c != "y"]
    m = lgb.LGBMClassifier(n_estimators=10, verbose=-1, min_child_samples=5).fit(d[feats], d["y"])
    path = tmp_path / "pooled_odds.json"
    path.write_text(json.dumps({"version": "t", "features": feats, "models": {"short": m.booster_.model_to_string()},
                                "weights": {"short": weight}, "base_rate": {"short": 0.3}}))
    return po.load_artifact(path), df, spy


def test_predict_pooled_blends_model_with_history(tmp_path):
    art, df, spy = _artifact(tmp_path, weight=0.3)
    out = po.predict_pooled("AAPL", df, "short", spy_df=spy, artifact=art)
    assert out["method"] == "pooled_blend"
    expect = 0.3 * out["prob_model"] + 0.7 * out["prob_hist"]
    assert out["prob"] == pytest.approx(expect, abs=2e-3)
    assert po.predict_pooled("AAPL", df, "medium", spy_df=spy, artifact=art) is None
    assert po.predict_pooled("BTC-USD", df, "short", spy_df=spy, artifact=art) is None


def test_missing_history_falls_back_to_base_rate(tmp_path, monkeypatch):
    art, df, spy = _artifact(tmp_path, weight=0.5)
    monkeypatch.setattr(po, "history_rate", lambda *a: None)
    out = po.predict_pooled("AAPL", df, "short", spy_df=spy, artifact=art)
    assert out["prob_hist"] is None
    assert out["prob"] == pytest.approx(0.5 * out["prob_model"] + 0.5 * 0.3, abs=2e-3)


def test_missing_artifact_falls_back_to_per_ticker(monkeypatch, tmp_path):
    monkeypatch.setattr(po, "ARTIFACT_PATH", tmp_path / "absent.json")
    out = predict_all_horizons("ZZTEST", _ohlcv(seed=5), inference_only=True)
    assert all(h["method"] == "per_ticker" for h in out.values())


def test_platt_calibration_skips_pooled_blend(monkeypatch):
    import signals.probability_calibration as pc
    monkeypatch.setattr(pc, "load_calibration_artifact", lambda p: {"short": {"a": 1, "b": -5}})
    monkeypatch.setattr(pc, "calibrate_probability", lambda p, k, a: 0.01)
    cfg = {"confidence": {"calibration": {"enabled": True, "path": "x"}}}
    out = apply_calibration_to_ml_horizons({"short": {"prob": 0.4, "method": "pooled_blend"},
                                            "medium": {"prob": 0.4, "method": "per_ticker"}}, cfg)
    assert out["short"]["prob"] == 0.4 and out["medium"]["prob"] == 0.01


def test_commodity_and_bond_etfs_show_history_only_odds():
    df = _ohlcv(seed=7)
    out = predict_all_horizons("GLD", df, inference_only=True)
    for k, h in out.items():
        assert h["method"] == "history_only" and h["model_weight"] == 0.0 and h["prob_model"] is None
        days = po.HORIZONS[k]["days"]
        assert h["prob"] == round(min(max(po.history_rate(df["close"], days, po.get_target_gain("GLD", k)), 0.02), 0.98), 3)
    assert po.predict_history_only("TLT", df, "short")["method"] == "history_only"
    assert po.predict_history_only("BTC-USD", df, "short")["method"] == "history_only"
    assert po.predict_history_only("AAPL", df, "short") is None
    assert po.predict_history_only("GLD", df.iloc[:50], "short") is None


def test_platt_calibration_skips_history_only(monkeypatch):
    import signals.probability_calibration as pc
    monkeypatch.setattr(pc, "load_calibration_artifact", lambda p: {"short": {"a": 1, "b": -5}})
    monkeypatch.setattr(pc, "calibrate_probability", lambda p, k, a: 0.01)
    cfg = {"confidence": {"calibration": {"enabled": True, "path": "x"}}}
    out = apply_calibration_to_ml_horizons({"short": {"prob": 0.4, "method": "history_only"}}, cfg)
    assert out["short"]["prob"] == 0.4
