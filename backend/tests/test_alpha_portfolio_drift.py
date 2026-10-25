import numpy as np
import pandas as pd

from signals.alpha.drift import calibration_drift, edge_decay, feature_drift, overall_status, psi
from signals.alpha.excess import build_cohort_expectancy, measured_kelly_inputs
from signals.alpha.pit_store import PITStore
from signals.alpha.portfolio import rank_and_pick


def test_rank_and_pick_caps_and_vol_target():
    rng = np.random.default_rng(0)
    base = rng.normal(0, 0.01, 200)
    rets = pd.DataFrame({
        "A": base + rng.normal(0, 0.002, 200),
        "B": base + rng.normal(0, 0.002, 200),  # highly correlated with A
        "C": rng.normal(0, 0.02, 200),
        "D": rng.normal(0, 0.01, 200),
        "E": rng.normal(0, 0.01, 200),
    })
    scores = pd.DataFrame({"p_beat_short": [0.7, 0.68, 0.66, 0.64, 0.4]}, index=list("ABCDE"))
    sectors = {"A": "Tech", "B": "Health", "C": "Tech", "D": "Tech"}
    out = rank_and_pick(scores, rets, sector_of=sectors, max_per_sector=2, max_pair_corr=0.8, target_vol=0.05, max_weight=0.6)
    tks = [p["ticker"] for p in out["picks"]]
    assert tks == ["A", "C"]
    assert "B" in out["skipped"] and "D" in out["skipped"] and "E" not in tks
    assert out["ex_ante_vol"] <= 0.0501
    assert out["gross_exposure"] < 1.0


def test_measured_kelly_inputs_shrinks_and_requires_n():
    recs = [{"entry_mode": "full_go", "composite_buy": 60, "excess_return_pct": 1.0, "actual_return_pct": r}
            for r in [5.0] * 30 + [-2.0] * 10]
    art = build_cohort_expectancy(recs, cost_pct=0.0)
    k = measured_kelly_inputs(entry_mode="full_go", score=60, artifact=art, min_n=30, prior_n=30)
    assert k["cohort"] == "mode_full_go|score_50_70"
    assert abs(k["win_rate"] - (0.75 * 40 + 15) / 70) < 1e-3
    assert k["avg_win_pct"] == 5.0 and k["avg_loss_pct"] == 2.0
    assert measured_kelly_inputs(entry_mode="full_go", score=60, artifact=art, min_n=100) is None


def test_pit_store_as_of_view(tmp_path):
    st = PITStore(tmp_path)
    st.append("feat", pd.DataFrame({"x": [1.0]}, index=["AAA"]), "2024-01-02", knowledge_time="2024-01-02T22:00:00Z")
    st.append("feat", pd.DataFrame({"x": [2.0]}, index=["AAA"]), "2024-01-03", knowledge_time="2024-01-03T22:00:00Z")
    st.append("feat", pd.DataFrame({"x": [9.0]}, index=["AAA"]), "2024-01-02", knowledge_time="2024-01-05T22:00:00Z")
    assert st.as_of_view("feat", "2024-01-02").loc["AAA", "x"] == 1.0
    assert st.as_of_view("feat", "2024-01-03").loc["AAA", "x"] == 2.0
    assert st.as_of_view("feat", "2024-01-06").loc["AAA", "x"] == 2.0


def test_drift_checks():
    rng = np.random.default_rng(1)
    ref = pd.DataFrame({"f": rng.normal(0, 1, 2000)})
    assert psi(ref["f"], pd.Series(rng.normal(0, 1, 2000))) < 0.05
    fd = feature_drift(ref, pd.DataFrame({"f": rng.normal(1.5, 1, 2000)}))
    assert fd["f"]["status"] == "alert"
    p = pd.Series(rng.uniform(0, 1, 2000))
    assert calibration_drift(p, (rng.uniform(0, 1, 2000) < p).astype(float))["status"] == "ok"
    assert edge_decay(pd.Series(rng.normal(-2, 1, 60)), expected_pct=1.0)["status"] == "alert"
    assert overall_status(fd) == "alert"
