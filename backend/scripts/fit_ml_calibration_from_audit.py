"""Fit ML calibration from live signal-audit API (or a local CSV).

Pulls ml_short_prob x resolved 30d returns, computes Brier + reliability bins,
fits Platt scaling for the short horizon, and derives ml_calibration_factor
(realized/predicted on overconfident slices — never > 1.0).

Example:
  python scripts/fit_ml_calibration_from_audit.py \\
    --api-base https://thrive-alpha.up.railway.app \\
    --out data/calibration/ml_horizons.json
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from signals.ml_calibration_store import brier_score, reliability_bins  # noqa: E402


def _norm_prob(raw: Any) -> float | None:
    try:
        p = float(raw)
    except (TypeError, ValueError):
        return None
    if p != p:
        return None
    if p > 1.5:
        p = p / 100.0
    return max(0.0, min(1.0, p))


def _fetch_records(api_base: str, *, page_size: int = 500, max_rows: int = 20000) -> list[dict]:
    base = api_base.rstrip("/")
    out: list[dict] = []
    offset = 0
    total = None
    while offset < max_rows:
        qs = urllib.parse.urlencode({"limit": page_size, "offset": offset})
        url = f"{base}/api/audit/records?{qs}"
        with urllib.request.urlopen(url, timeout=180) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        batch = payload.get("records") or []
        total = int(payload.get("total") or 0)
        out.extend(batch)
        offset += page_size
        print(f"fetched offset={offset} batch={len(batch)} total_api={total} kept={len(out)}")
        if not batch or (total is not None and offset >= total):
            break
    return out


def _pairs_from_records(records: list[dict]) -> tuple[list[float], list[int], list[dict]]:
    probs: list[float] = []
    ys: list[int] = []
    meta: list[dict] = []
    for r in records:
        p = _norm_prob(r.get("ml_short_prob"))
        ret = r.get("return_30d_pct")
        if p is None or ret is None:
            continue
        try:
            ret_f = float(ret)
        except (TypeError, ValueError):
            continue
        y = 1 if ret_f > 0 else 0
        probs.append(p)
        ys.append(y)
        meta.append(
            {
                "ticker": r.get("ticker"),
                "signal_date": r.get("signal_date"),
                "ml_signal": r.get("ml_signal"),
                "verdict": r.get("verdict"),
                "return_30d_pct": ret_f,
                "go_no_go": r.get("go_no_go"),
                "prob": p,
            }
        )
    return probs, ys, meta


def _fit_platt(probs: list[float], ys: list[int]) -> tuple[float, float]:
    try:
        import numpy as np
        from sklearn.linear_model import LogisticRegression
    except ImportError as e:
        raise SystemExit(f"sklearn/numpy required: {e}") from e

    eps = 1e-6
    X = np.array(
        [
            [
                math.log(
                    max(eps, min(1 - eps, p))
                    / max(eps, 1.0 - max(eps, min(1 - eps, p)))
                )
            ]
            for p in probs
        ]
    )
    y = np.array(ys, dtype=int)
    if len(np.unique(y)) < 2 or len(y) < 30:
        return 1.0, 0.0
    lr = LogisticRegression(solver="lbfgs", max_iter=1000)
    lr.fit(X, y)
    return float(lr.coef_[0][0]), float(lr.intercept_[0])


def _apply_platt(p: float, a: float, b: float) -> float:
    eps = 1e-6
    p = max(eps, min(1 - eps, p))
    z = math.log(p / (1 - p))
    return 1.0 / (1.0 + math.exp(-(a * z + b)))


def _slice_factor(meta: list[dict], *, predicate) -> dict[str, Any]:
    rows = [m for m in meta if predicate(m)]
    if len(rows) < 20:
        return {"n": len(rows), "factor": None, "note": "insufficient_n"}
    mean_p = sum(m["prob"] for m in rows) / len(rows)
    realized = sum(1 for m in rows if m["return_30d_pct"] > 0) / len(rows)
    avg_ret = sum(m["return_30d_pct"] for m in rows) / len(rows)
    factor = max(0.5, min(1.0, (realized / mean_p) if mean_p > 1e-6 else 1.0))
    return {
        "n": len(rows),
        "mean_predicted": round(mean_p, 4),
        "realized_pos_rate": round(realized, 4),
        "avg_return_30d_pct": round(avg_ret, 3),
        "factor": round(factor, 4),
    }


def build_artifact(
    probs: list[float],
    ys: list[int],
    meta: list[dict],
    *,
    source: str,
) -> dict[str, Any]:
    bins = reliability_bins(probs, ys)
    brier = brier_score(probs, ys)
    a, b = _fit_platt(probs, ys)
    cal_probs = [_apply_platt(p, a, b) for p in probs]
    brier_cal = brier_score(cal_probs, ys)

    buy_slice = _slice_factor(
        meta,
        predicate=lambda m: "BUY" in str(m.get("ml_signal") or "").upper(),
    )
    hi_slice = _slice_factor(meta, predicate=lambda m: m["prob"] >= 0.50)
    mid_hi = _slice_factor(meta, predicate=lambda m: m["prob"] >= 0.45)

    candidates = [
        s["factor"] for s in (buy_slice, hi_slice, mid_hi) if s.get("factor") is not None
    ]
    factor = min(candidates) if candidates else 1.0
    factor = max(0.5, min(1.0, float(factor)))

    return {
        "method": "platt",
        "fitted_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": source,
        "label": "y = 1 if return_30d_pct > 0 (path-unaware close-to-close)",
        "era_note": (
            "Audit spans model/gate fine-tunes; win% can look fine while avg returns "
            "lag when losses are larger than wins. Treat as provisional — refit after "
            "stable gate era accumulates ~30+ trading days."
        ),
        "n": len(probs),
        "mean_predicted": round(sum(probs) / len(probs), 4) if probs else None,
        "realized_pos_rate": round(sum(ys) / len(ys), 4) if ys else None,
        "brier_raw": round(brier, 4) if brier is not None else None,
        "brier_calibrated": round(brier_cal, 4) if brier_cal is not None else None,
        "reliability": bins,
        "slices": {
            "ml_buy": buy_slice,
            "prob_ge_0_50": hi_slice,
            "prob_ge_0_45": mid_hi,
        },
        "ml_calibration_factor": round(factor, 3),
        "ml_calibration_factor_rule": (
            "min(realized/predicted) over BUY and high-prob slices; clip [0.5, 1.0]"
        ),
        "short": {"a": round(a, 6), "b": round(b, 6), "n": len(probs)},
        "medium": {
            "a": 1.0,
            "b": 0.0,
            "n": 0,
            "note": "no medium-horizon probs in audit export — identity",
        },
        "long": {
            "a": 1.0,
            "b": 0.0,
            "n": 0,
            "note": "no long-horizon probs in audit export — identity",
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Fit ML calibration from signal audit")
    ap.add_argument(
        "--api-base",
        type=str,
        default="https://thrive-alpha.up.railway.app",
    )
    ap.add_argument(
        "--csv",
        type=str,
        default=None,
        help="Optional local CSV with ml_short_prob,return_30d_pct",
    )
    ap.add_argument("--out", type=str, default="data/calibration/ml_horizons.json")
    ap.add_argument("--min-n", type=int, default=100)
    args = ap.parse_args()

    if args.csv:
        path = Path(args.csv)
        if not path.is_absolute():
            path = ROOT / path
        records = list(csv.DictReader(path.open(encoding="utf-8")))
        source = f"csv:{path}"
    else:
        records = _fetch_records(args.api_base)
        source = f"api:{args.api_base.rstrip('/')}/api/audit/records"

    probs, ys, meta = _pairs_from_records(records)
    print(f"paired n={len(probs)} from {len(records)} records")
    if len(probs) < args.min_n:
        raise SystemExit(
            f"Need >= {args.min_n} resolved pairs with ml_short_prob; got {len(probs)}"
        )

    art = build_artifact(probs, ys, meta, source=source)
    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = ROOT / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(art, f, indent=2)
        f.write("\n")
    print(
        json.dumps(
            {
                "written": str(out_path),
                "n": art["n"],
                "brier_raw": art["brier_raw"],
                "brier_calibrated": art["brier_calibrated"],
                "ml_calibration_factor": art["ml_calibration_factor"],
                "slices": art["slices"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
