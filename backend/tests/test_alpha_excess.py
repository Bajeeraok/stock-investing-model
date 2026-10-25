from signals.alpha.excess import (
    build_cohort_expectancy,
    cohort_keys,
    excess_return_pct,
    load_artifact,
    prefer_index_decision,
    prefer_index_for_payload,
    save_artifact,
    score_bucket,
    summarize_excess,
)
from signals.forward_tracking_metrics import aggregate_horizon_stats


def _recs(mode, score, excess, n):
    return [{"entry_mode": mode, "composite_buy": score, "excess_return_pct": excess, "horizon_days": 20}] * n


def test_score_bucket_and_keys():
    assert score_bucket(29.9) == "0_30"
    assert score_bucket(30) == "30_50"
    assert score_bucket(85) == "70_100"
    assert score_bucket(None) is None
    assert cohort_keys("full_go", 40) == ["mode_full_go|score_30_50", "mode_full_go", "score_30_50", "all"]


def test_excess_return_pct():
    assert excess_return_pct(5.0, 2.0) == 3.0
    assert excess_return_pct(None, 2.0) is None


def test_summarize_excess_shrinks_small_samples():
    s = summarize_excess([2.0] * 10, cost_pct=0.3, prior_n=30)
    assert s["n"] == 10
    assert s["net_excess_pct"] == 1.7
    assert abs(s["shrunk_net_excess_pct"] - 1.7 * 10 / 40) < 1e-3


def test_prefer_index_when_cohort_trails():
    art = build_cohort_expectancy(
        _recs("starter_only", 80, -1.0, 40) + _recs("full_go", 40, 3.0, 40), horizon_days=20, cost_pct=0.3
    )
    d = prefer_index_decision(entry_mode="starter_only", score=80, artifact=art, min_n=30)
    assert d["prefer_index"] is True
    assert d["cohort"] == "mode_starter_only|score_70_100"
    g = prefer_index_decision(entry_mode="full_go", score=40, artifact=art, min_n=30)
    assert g["prefer_index"] is False


def test_prefer_index_insufficient_data_does_not_override():
    art = build_cohort_expectancy(_recs("full_go", 40, -5.0, 5), cost_pct=0.3)
    d = prefer_index_decision(entry_mode="full_go", score=40, artifact=art, min_n=30)
    assert d["prefer_index"] is None


def test_payload_wrapper_respects_config_and_mode(tmp_path):
    p = save_artifact(build_cohort_expectancy(_recs("full_go", 80, -2.0, 50)), tmp_path / "c.json")
    cfg = {"alpha": {"prefer_index": {"enabled": True, "min_n": 30}}}
    assert prefer_index_for_payload(entry_mode="hard_lock", score=80, config=cfg, artifact_path=p) is None
    assert prefer_index_for_payload(entry_mode="full_go", score=80, config=cfg, artifact_path=p)["prefer_index"]
    off = {"alpha": {"prefer_index": {"enabled": False}}}
    assert prefer_index_for_payload(entry_mode="full_go", score=80, config=off, artifact_path=p) is None
    assert load_artifact(tmp_path / "missing.json") is None


def test_aggregate_horizon_stats_reports_excess():
    rows = [
        {"actual_return_pct": 3.0, "excess_return_pct": 1.0},
        {"actual_return_pct": -1.0, "excess_return_pct": -2.0},
    ]
    out = aggregate_horizon_stats(rows, quality_only=False)
    assert out["avg_excess_return_pct"] == -0.5
    assert out["beat_benchmark_pct"] == 50.0


def test_summarize_excess_clusters_by_date_and_overlap():
    from signals.alpha.excess import summarize_excess

    # 40 dates x 10 names, all names on a date share the same excess
    vals, dates = [], []
    for i in range(40):
        for _ in range(10):
            vals.append(1.0 if i % 2 else -0.5)
            dates.append(f"d{i}")
    naive = summarize_excess(vals)
    adj = summarize_excess(vals, dates=dates, horizon_days=5)
    assert adj["n_dates"] == 40 and adj["n_eff"] == 8.0
    assert abs(adj["t_stat"]) < abs(naive["t_stat"])
    assert adj["t_stat_naive"] == naive["t_stat"]
    assert adj["ci95_low_pct"] < naive["ci95_low_pct"]


def test_summarize_excess_too_few_independent_periods():
    from signals.alpha.excess import summarize_excess

    out = summarize_excess([1.0, 2.0, 3.0], dates=["a", "b", "c"], horizon_days=21)
    assert out["t_stat"] is None and out["ci95_low_pct"] is None
