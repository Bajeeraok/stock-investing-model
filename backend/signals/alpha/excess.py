"""
Excess-return-vs-benchmark cohort statistics and the "prefer index" decision.

A signal cohort only earns a BUY/STARTER if its measured forward return beats simply
owning the benchmark (SPY) after round-trip costs. Cohorts are keyed by entry mode and
composite-score bucket; small cohorts are shrunk toward zero excess so a lucky handful
of trades cannot unlock a verdict.
"""
from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any, Iterable

BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_ARTIFACT_PATH = BACKEND_ROOT / "data" / "alpha" / "cohort_expectancy.json"

ACTIONABLE_ENTRY_MODES = ("starter_only", "full_go")

_ARTIFACT_CACHE: dict[str, tuple[float, dict[str, Any] | None]] = {}


def _f(x: Any) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def score_bucket(score: Any) -> str | None:
    s = _f(score)
    if s is None:
        return None
    if s < 30:
        return "0_30"
    if s < 50:
        return "30_50"
    if s < 70:
        return "50_70"
    return "70_100"


def excess_return_pct(ret_pct: Any, benchmark_ret_pct: Any) -> float | None:
    r, b = _f(ret_pct), _f(benchmark_ret_pct)
    if r is None or b is None:
        return None
    return round(r - b, 4)


def record_entry_mode(record: dict[str, Any]) -> str | None:
    em = record.get("entry_mode") or (record.get("retail_status") or {}).get("entry_mode")
    return str(em).lower() if em else None


def record_score(record: dict[str, Any]) -> float | None:
    for k in ("composite_buy", "score", "buy_score"):
        v = _f(record.get(k))
        if v is not None:
            return v
    return None


def cohort_keys(entry_mode: str | None, score: Any) -> list[str]:
    """Cohort keys from most specific to least specific (``all`` last)."""
    b = score_bucket(score)
    em = str(entry_mode).lower() if entry_mode else None
    keys: list[str] = []
    if em and b:
        keys.append(f"mode_{em}|score_{b}")
    if em:
        keys.append(f"mode_{em}")
    if b:
        keys.append(f"score_{b}")
    keys.append("all")
    return keys


def summarize_excess(
    values: Iterable[float],
    *,
    cost_pct: float = 0.0,
    prior_n: float = 30.0,
) -> dict[str, Any]:
    """Mean/beat-rate/t-stat of excess returns, net of cost, with shrinkage toward 0."""
    xs = [float(v) for v in values if _f(v) is not None]
    n = len(xs)
    if n == 0:
        return {"n": 0}
    mean = sum(xs) / n
    var = sum((x - mean) ** 2 for x in xs) / (n - 1) if n > 1 else 0.0
    std = math.sqrt(var)
    se = std / math.sqrt(n) if n > 1 else float("inf")
    net = mean - cost_pct
    shrink = n / (n + max(prior_n, 0.0))
    return {
        "n": n,
        "mean_excess_pct": round(mean, 4),
        "net_excess_pct": round(net, 4),
        "shrunk_net_excess_pct": round(net * shrink, 4),
        "beat_benchmark_pct": round(100.0 * sum(1 for x in xs if x > cost_pct) / n, 2),
        "std_pct": round(std, 4),
        "t_stat": round(net / se, 3) if se not in (0.0, float("inf")) else None,
        "ci95_low_pct": round(net - 1.96 * se, 4) if math.isfinite(se) else None,
        "ci95_high_pct": round(net + 1.96 * se, 4) if math.isfinite(se) else None,
    }


def build_cohort_expectancy(
    records: Iterable[dict[str, Any]],
    *,
    horizon_days: int | None = None,
    cost_pct: float = 0.30,
    prior_n: float = 30.0,
    benchmark: str = "SPY",
    excess_field: str = "excess_return_pct",
) -> dict[str, Any]:
    """Group records by cohort and summarize excess returns. Records need ``excess_field``."""
    buckets: dict[str, list[float]] = {}
    rets: dict[str, list[float]] = {}
    for r in records:
        if horizon_days is not None and r.get("horizon_days") not in (None, horizon_days):
            continue
        exc = _f(r.get(excess_field))
        if exc is None:
            continue
        ret = _f(r.get("actual_return_pct"))
        for k in cohort_keys(record_entry_mode(r), record_score(r)):
            buckets.setdefault(k, []).append(exc)
            if ret is not None:
                rets.setdefault(k, []).append(ret)
    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "benchmark": benchmark,
        "horizon_days": horizon_days,
        "cost_pct": cost_pct,
        "prior_n": prior_n,
        "cohorts": {
            k: {**summarize_excess(v, cost_pct=cost_pct, prior_n=prior_n), **summarize_payoff(rets.get(k, []), cost_pct=cost_pct)}
            for k, v in sorted(buckets.items())
        },
    }


def summarize_payoff(returns: Iterable[float], *, cost_pct: float = 0.0) -> dict[str, Any]:
    """Measured win rate and average win / loss of after-cost absolute returns (percent)."""
    net = [float(x) - cost_pct for x in returns]
    if not net:
        return {}
    wins = [x for x in net if x > 0]
    losses = [-x for x in net if x <= 0]
    return {
        "n_ret": len(net),
        "win_rate": round(len(wins) / len(net), 4),
        "avg_win_pct": round(sum(wins) / len(wins), 3) if wins else 0.0,
        "avg_loss_pct": round(sum(losses) / len(losses), 3) if losses else 0.0,
    }


def measured_kelly_inputs(
    *,
    entry_mode: str | None,
    score: Any,
    artifact: dict[str, Any] | None = None,
    min_n: int = 30,
    prior_n: float = 30.0,
) -> dict[str, Any] | None:
    """
    Win rate / avg win / avg loss for sizing from the most specific cohort with ``min_n``
    tracked outcomes. Win rate is shrunk toward 50% with ``prior_n`` pseudo-observations so
    a lucky small cohort cannot drive an oversized Kelly fraction. None when unmeasured.
    """
    art = artifact if artifact is not None else load_artifact()
    cohorts = (art or {}).get("cohorts") or {}
    for k in cohort_keys(entry_mode, score):
        c = cohorts.get(k) or {}
        n = int(c.get("n_ret") or 0)
        if n >= min_n and c.get("avg_loss_pct"):
            wr = (c["win_rate"] * n + 0.5 * prior_n) / (n + prior_n)
            return {
                "cohort": k,
                "n": n,
                "win_rate": round(wr, 4),
                "avg_win_pct": float(c["avg_win_pct"]),
                "avg_loss_pct": float(c["avg_loss_pct"]),
            }
    return None


def save_artifact(artifact: dict[str, Any], path: str | Path | None = None) -> Path:
    p = Path(path) if path else DEFAULT_ARTIFACT_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")
    _ARTIFACT_CACHE.pop(str(p), None)
    return p


def load_artifact(path: str | Path | None = None) -> dict[str, Any] | None:
    p = Path(path) if path else DEFAULT_ARTIFACT_PATH
    try:
        mtime = p.stat().st_mtime
    except OSError:
        return None
    hit = _ARTIFACT_CACHE.get(str(p))
    if hit and hit[0] == mtime:
        return hit[1]
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = None
    _ARTIFACT_CACHE[str(p)] = (mtime, data)
    return data


def prefer_index_decision(
    *,
    entry_mode: str | None,
    score: Any,
    artifact: dict[str, Any] | None,
    min_n: int = 30,
) -> dict[str, Any] | None:
    """
    Decide whether to recommend the benchmark instead of this setup.

    Uses the most specific cohort with at least ``min_n`` observations. ``prefer_index``
    is True when that cohort's shrunk excess return after costs is not above zero, False
    when it is, and None when no cohort has enough data (no override).
    """
    if not artifact:
        return None
    cohorts = artifact.get("cohorts") or {}
    benchmark = str(artifact.get("benchmark") or "SPY")
    for key in cohort_keys(entry_mode, score):
        if key == "all":
            continue
        st = cohorts.get(key) or {}
        if int(st.get("n") or 0) < min_n:
            continue
        shrunk = _f(st.get("shrunk_net_excess_pct"))
        if shrunk is None:
            continue
        prefer = shrunk <= 0
        ci_low = _f(st.get("ci95_low_pct"))
        verb = "trailed" if prefer else "beat"
        return {
            "prefer_index": prefer,
            "edge_confirmed": bool(ci_low is not None and ci_low > 0),
            "benchmark": benchmark,
            "cohort": key,
            "n": int(st["n"]),
            "net_excess_pct": st.get("net_excess_pct"),
            "shrunk_net_excess_pct": shrunk,
            "beat_benchmark_pct": st.get("beat_benchmark_pct"),
            "horizon_days": artifact.get("horizon_days"),
            "reason": (
                f"Similar setups ({key}, n={int(st['n'])}) {verb} {benchmark} by "
                f"{abs(float(st.get('net_excess_pct') or 0)):.2f}% after costs"
                + (f" over {artifact.get('horizon_days')} days" if artifact.get("horizon_days") else "")
            ),
        }
    return {
        "prefer_index": None,
        "edge_confirmed": False,
        "benchmark": benchmark,
        "cohort": None,
        "reason": f"Not enough tracked outcomes (need {min_n}) to compare this setup with {benchmark}",
    }


def _prefer_index_cfg(config: dict | None) -> dict[str, Any]:
    if config is None:
        try:
            from config_loader import load_config

            config = load_config()
        except Exception:
            config = {}
    return ((config or {}).get("alpha") or {}).get("prefer_index") or {}


def prefer_index_for_payload(
    *,
    entry_mode: str | None,
    score: Any,
    config: dict | None = None,
    artifact_path: str | Path | None = None,
) -> dict[str, Any] | None:
    """Config-aware wrapper used by the retail action payload. None = feature off / no artifact."""
    cfg = _prefer_index_cfg(config)
    if not cfg.get("enabled", True):
        return None
    if str(entry_mode or "").lower() not in ACTIONABLE_ENTRY_MODES:
        return None
    path = artifact_path or cfg.get("artifact_path")
    if path and not Path(path).is_absolute():
        path = BACKEND_ROOT / path
    return prefer_index_decision(
        entry_mode=entry_mode,
        score=score,
        artifact=load_artifact(path),
        min_n=int(cfg.get("min_n", 30)),
    )
