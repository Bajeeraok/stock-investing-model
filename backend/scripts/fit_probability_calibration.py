"""
Fit Platt scaling (logistic on logit(p)) for each ML horizon from a CSV of validation outcomes.

CSV columns: horizon (short|medium|long), prob (0-1), y (0/1 event occurred).

Writes backend/data/calibration/ml_horizons.json for confidence.calibration.enabled.

  cd backend && python scripts/fit_probability_calibration.py --csv data/calibration/val_probs.csv --out data/calibration/ml_horizons.json
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _fit_platt(probs: list[float], ys: list[int]) -> tuple[float, float]:
    try:
        from sklearn.linear_model import LogisticRegression
        import numpy as np
    except ImportError as e:
        raise SystemExit(f"sklearn required: {e}") from e
    eps = 1e-9
    X = []
    for p in probs:
        p = float(np.clip(p, eps, 1.0 - eps))
        X.append([math.log(p / (1.0 - p))])
    X = np.array(X)
    y = np.array(ys, dtype=int)
    if len(np.unique(y)) < 2:
        return 1.0, 0.0
    lr = LogisticRegression(solver="lbfgs", random_state=42)
    lr.fit(X, y)
    a = float(lr.coef_[0][0])
    b = float(lr.intercept_[0])
    return a, b


def _fit_isotonic(probs: list[float], ys: list[int], n_knots: int = 20) -> list[dict]:
    """Fit isotonic regression, return downsampled knots [{x,y}].

    With large n (>= ~2000), isotonic captures the true reliability curve
    better than 2-param Platt — non-parametric, only requires monotonicity.
    Knots are quantile-binned so the artifact stays small.
    """
    import numpy as np
    from sklearn.isotonic import IsotonicRegression

    x = np.asarray(probs, dtype=float)
    y = np.asarray(ys, dtype=float)
    ir = IsotonicRegression(out_of_bounds="clip")
    ir.fit(x, y)

    # Quantile grid of x -> calibrated y
    qs = np.linspace(0.0, 1.0, n_knots + 1)
    xs = np.quantile(x, qs)
    xs[0], xs[-1] = 0.0, 1.0
    ys_hat = ir.predict(xs)
    knots = [
        {"x": round(float(a), 4), "y": round(float(b), 4)}
        for a, b in zip(xs, ys_hat)
    ]
    # Dedup consecutive identical knots
    deduped = []
    for k in knots:
        if deduped and abs(k["x"] - deduped[-1]["x"]) < 1e-6 and abs(k["y"] - deduped[-1]["y"]) < 1e-6:
            continue
        deduped.append(k)
    return deduped


def main() -> None:
    ap = argparse.ArgumentParser(description="Fit calibration for ML horizons")
    ap.add_argument("--csv", type=str, required=True)
    ap.add_argument("--out", type=str, default="data/calibration/ml_horizons.json")
    ap.add_argument("--method", type=str, default="auto",
                    choices=["auto", "platt", "isotonic"],
                    help="auto = isotonic when n>=1000 per horizon else platt")
    ap.add_argument("--knots", type=int, default=20, help="isotonic knot count")
    args = ap.parse_args()

    path = Path(args.csv)
    if not path.is_absolute():
        path = ROOT / path
    by_h: dict[str, list[tuple[float, int]]] = defaultdict(list)
    with open(path, encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            h = (row.get("horizon") or "").strip().lower()
            if h not in ("short", "medium", "long"):
                continue
            p = float(row["prob"])
            y = int(float(row["y"]))
            by_h[h].append((p, y))

    out: dict = {"method": args.method}
    for h in ("short", "medium", "long"):
        pairs = by_h.get(h) or []
        if len(pairs) < 20:
            out[h] = {"a": 1.0, "b": 0.0, "note": "insufficient rows — identity"}
            continue
        probs = [x[0] for x in pairs]
        ys = [x[1] for x in pairs]
        method = args.method
        if method == "auto":
            method = "isotonic" if len(pairs) >= 1000 else "platt"
        if method == "isotonic":
            out[h] = {
                "method": "isotonic",
                "knots": _fit_isotonic(probs, ys, args.knots),
                "n": len(pairs),
            }
        else:
            a, b = _fit_platt(probs, ys)
            out[h] = {"a": round(a, 6), "b": round(b, 6), "n": len(pairs)}
        out["method"] = method

    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = ROOT / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print(json.dumps({"written": str(out_path), "artifact": out}, indent=2))


if __name__ == "__main__":
    main()
