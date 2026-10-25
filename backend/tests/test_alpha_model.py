import numpy as np
import pandas as pd

from signals.alpha.features import build_panel
from signals.alpha.labels import excess_label, triple_barrier_label
from signals.alpha.pooled_model import WalkForwardConfig, predict_latest, train_all, walk_forward_folds
from signals.alpha.stacker import LAYERS, fit_layer_weights, learned_horizon_weights, save_weights
from signals.alpha.universe import members_on, membership_from_tables, membership_mask


def _ohlcv(n, seed, drift=0.0003):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2012-01-02", periods=n)
    c = 100 * np.exp(np.cumsum(rng.normal(drift, 0.015, n)))
    return pd.DataFrame(
        {"open": c, "high": c * 1.01, "low": c * 0.99, "close": c, "volume": rng.integers(1e6, 2e6, n)}, index=idx
    )


def test_triple_barrier_target_first_and_stop_first():
    idx = pd.bdate_range("2020-01-01", periods=40)
    c = pd.Series(100.0, index=idx)
    hi, lo = c + 1, c - 1  # ATR = 2
    up = hi.copy()
    up.iloc[20] = 110
    lab = triple_barrier_label(c, up, lo, 5)
    assert lab.iloc[16] == 1.0
    dn = lo.copy()
    dn.iloc[20] = 90
    assert triple_barrier_label(c, hi, dn, 5).iloc[16] == 0.0
    assert np.isnan(lab.iloc[-1])


def test_excess_label_uses_benchmark():
    idx = pd.bdate_range("2020-01-01", periods=10)
    c = pd.Series(np.linspace(100, 110, 10), index=idx)
    b = pd.Series(np.linspace(100, 101, 10), index=idx)
    lab = excess_label(c, b, 3)
    assert lab.iloc[0] == 1.0 and np.isnan(lab.iloc[-1])


def test_walk_forward_folds_are_purged_and_before_holdout():
    dates = list(range(2000))
    cfg = WalkForwardConfig(min_train_days=500, step_days=200, holdout_days=300)
    folds = list(walk_forward_folds(dates, 20, cfg))
    assert folds
    for tr, te in folds:
        assert te[0] - tr[-1] == 21
        assert te[-1] < 1700


def test_pooled_model_trains_and_predicts():
    data = {"SPY": _ohlcv(1300, 0)}
    for i in range(12):
        data[f"T{i}"] = _ohlcv(1300, i + 1, drift=0.0001 * i)

    def labels(tk, df, b):
        from scripts.train_alpha_model import make_labels

        return make_labels(0.003)(tk, df, b)

    panel = build_panel(data, extra_label_fn=labels)
    cfg = WalkForwardConfig(min_train_days=400, step_days=200, holdout_days=150, n_estimators=30, min_child_samples=20)
    art = train_all(panel, cfg, horizons=["short"])
    hm = art["horizons"]["short"]
    assert hm["walk_forward_folds"] >= 1
    assert "auc_beat" in hm["walk_forward_metrics"]
    pred = predict_latest(art, panel, require_promoted=False)
    assert {"p_beat_short", "p_tb_short", "ret_q50_short"} <= set(pred.columns)
    assert pred["p_beat_short"].between(0, 1).all()


def test_membership_ranges_and_mask():
    current = pd.DataFrame({"Symbol": ["AAA", "BRK.B"], "GICS Sector": ["Energy", "Financials"], "Date added": ["2015-01-01", "2000-01-01"]})
    changes = pd.DataFrame({"Date": ["2018-06-01"], "Added Ticker": ["AAA2"], "Removed Ticker": ["OLD"]})
    m = membership_from_tables(current, changes)
    assert "BRK-B" in set(m["ticker"])
    assert "OLD" in members_on(m, "2017-01-01") and "OLD" not in members_on(m, "2019-01-01")
    idx = pd.MultiIndex.from_tuples(
        [(pd.Timestamp("2014-01-01"), "AAA"), (pd.Timestamp("2016-01-01"), "AAA"), (pd.Timestamp("2019-01-01"), "OLD")],
        names=["date", "ticker"],
    )
    mask = membership_mask(pd.DataFrame(index=idx, data={"x": [1, 2, 3]}), m)
    assert mask.tolist() == [False, True, False]


def test_stacker_accepts_only_when_better(tmp_path):
    rng = np.random.default_rng(0)
    rows = []
    for i in range(400):
        s = {k: float(rng.uniform()) for k in LAYERS}
        rows.append({"as_of_date": f"2024-{i:04d}", "layer_scores": s, "excess_return_pct": 5 * s["insider_signal"] + rng.normal(0, 0.5)})
    default = {k: (1.0 if k == "nlp_sentiment" else 0.0) for k in LAYERS}
    res = fit_layer_weights(rows, default)
    assert res["accepted"] and max(res["weights"], key=res["weights"].get) == "insider_signal"
    p = save_weights({"short": res}, tmp_path / "w.json")
    assert learned_horizon_weights("short", p)["insider_signal"] > 0.5
    assert learned_horizon_weights("medium", p) is None
    assert not fit_layer_weights(rows[:50], default)["accepted"]
