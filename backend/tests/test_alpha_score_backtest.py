import numpy as np
import pandas as pd

from signals.alpha.score_backtest import analyze, bucket_of, rank_ic


def _panel(signal: float, n_dates: int = 120, n_names: int = 30, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2018-01-01", periods=n_dates * 5)[::5]
    rows = []
    for d in dates:
        common = rng.normal(0, 2)
        for k in range(n_names):
            s = rng.uniform(0, 100)
            ex = common + signal * (s - 50) / 10 + rng.normal(0, 3)
            rows.append({
                "as_of_date": d.strftime("%Y-%m-%d"), "ticker": f"T{k}", "sector": "Tech" if k % 2 else "Energy",
                "score": s, "score_raw": s, "style": "TRENDING", "spy_regime": "bull",
                "trend_score": s, "rsi_contrib": rng.uniform(0, 100), "macd_contrib": rng.uniform(0, 100),
                "ret_21": ex, "excess_21": ex,
            })
    return pd.DataFrame(rows)


def test_bucket_of():
    assert bucket_of(0) == "0-30" and bucket_of(49.9) == "30-50" and bucket_of(100) == "70-100"
    assert bucket_of(float("nan")) is None


def test_rank_ic_detects_signal_and_noise():
    strong = rank_ic(_panel(1.0), "score", 21, 5)
    noise = rank_ic(_panel(0.0), "score", 21, 5)
    assert strong["ic_mean"] > 0.2 and strong["ic_t"] > 3
    assert abs(noise["ic_mean"]) < 0.05
    assert strong["n_eff"] == round(strong["n_dates"] / 4, 1)


def test_analyze_bucket_ordering():
    rep = analyze(_panel(1.0), [21], 5, 0.3)
    b = rep["horizons"]["21"]["buckets"]
    assert b["70-100"]["net_excess_pct"] > b["0-30"]["net_excess_pct"]
    assert set(rep["horizons"]["21"]["by_sector"]) == {"Tech", "Energy"}
    assert rep["horizons"]["21"]["ic"]["score"]["ic_mean"] > 0
