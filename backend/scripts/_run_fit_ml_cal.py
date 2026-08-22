"""One-shot patch + fit runner for ML calibration."""
from __future__ import annotations

import json
import math
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from signals.ml_calibration_store import brier_score, reliability_bins

API_BASE = "https://thrive-alpha.up.railway.app"
OUT = ROOT / "data" / "calibration" / "ml_horizons.json"


def norm_prob(raw):
    try:
        p = float(raw)
    except (TypeError, ValueError):
        return None
    if p != p:
        return None
    if p > 1.5:
        p /= 100.0
    return max(0.0, min(1.0, p))


def fetch_all():
    out = []
    offset = 0
    while True:
        qs = urllib.parse.urlencode({"limit": 500, "offset": offset})
        url = f"{API_BASE}/api/audit/records?{qs}"
        with urllib.request.urlopen(url, timeout=180) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        batch = payload.get("records") or []
        total = int(payload.get("total") or 0)
        out.extend(batch)
        offset += 500
        print(f"offset={offset} batch={len(batch)} total={total} kept={len(out)}")
        if not batch or offset >= total:
            break
    return out


def pairs(records):
    probs, ys, meta = [], [], []
    for r in records:
        p = norm_prob(r.get("ml_short_prob"))
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
                "ml_signal": r.get("ml_signal"),
                "return_30d_pct": ret_f,
                "prob": p,
                "verdict": r.get("verdict"),
            }
        )
    return probs, ys, meta


def fit_platt(probs, ys):
    import numpy as np
    from sklearn.linear_model import LogisticRegression

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


def apply_platt(p, a, b):
    eps = 1e-6
    p = max(eps, min(1 - eps, p))
    z = math.log(p / (1 - p))
    return 1.0 / (1.0 + math.exp(-(a * z + b)))


def slice_factor(meta, pred):
    rows = [m for m in meta if pred(m)]
    if len(rows) < 20:
        return {"n": len(rows), "factor": None, "note": "insufficient_n"}
    mean_p = sum(m["prob"] for m in rows) / len(rows)
    realized = sum(1 for m in rows if m["return_30d_pct"] > 0) / len(rows)
    avg_ret = sum(m["return_30d_pct"] for m in rows) / len(rows)
    factor = max(0.5, min(1.0, realized / mean_p if mean_p > 1e-6 else 1.0))
    return {
        "n": len(rows),
        "mean_predicted": round(mean_p, 4),
        "realized_pos_rate": round(realized, 4),
        "avg_return_30d_pct": round(avg_ret, 3),
        "factor": round(factor, 4),
    }


def main():
    records = fetch_all()
    probs, ys, meta = pairs(records)
    print(f"paired n={len(probs)}")
    if len(probs) < 100:
        raise SystemExit(f"too few pairs: {len(probs)}")

    bins = reliability_bins(probs, ys)
    brier = brier_score(probs, ys)
    a, b = fit_platt(probs, ys)
    cal = [apply_platt(p, a, b) for p in probs]
    brier_cal = brier_score(cal, ys)

    buy = slice_factor(meta, lambda m: "BUY" in str(m.get("ml_signal") or "").upper())
    hi = slice_factor(meta, lambda m: m["prob"] >= 0.50)
    mid = slice_factor(meta, lambda m: m["prob"] >= 0.45)
    cands = [s["factor"] for s in (buy, hi, mid) if s.get("factor") is not None]
    factor = max(0.5, min(1.0, min(cands) if cands else 1.0))

    art = {
        "method": "platt",
        "fitted_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": f"api:{API_BASE}/api/audit/records",
        "label": "y = 1 if return_30d_pct > 0 (path-unaware close-to-close)",
        "era_note": (
            "Audit spans model/gate fine-tunes; win% can look fine while avg returns "
            "lag when losses are larger than wins. Provisional — refit after stable "
            "gate era accumulates ~30+ trading days."
        ),
        "n": len(probs),
        "mean_predicted": round(sum(probs) / len(probs), 4),
        "realized_pos_rate": round(sum(ys) / len(ys), 4),
        "brier_raw": round(brier, 4) if brier is not None else None,
        "brier_calibrated": round(brier_cal, 4) if brier_cal is not None else None,
        "reliability": bins,
        "slices": {"ml_buy": buy, "prob_ge_0_50": hi, "prob_ge_0_45": mid},
        "ml_calibration_factor": round(factor, 3),
        "ml_calibration_factor_rule": (
            "min(realized/predicted) over BUY and high-prob slices; clip [0.5, 1.0]"
        ),
        "short": {"a": round(a, 6), "b": round(b, 6), "n": len(probs)},
        "medium": {"a": 1.0, "b": 0.0, "n": 0, "note": "identity — no medium probs in audit"},
        "long": {"a": 1.0, "b": 0.0, "n": 0, "note": "identity — no long probs in audit"},
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(art, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "written": str(OUT),
        "n": art["n"],
        "brier_raw": art["brier_raw"],
        "brier_calibrated": art["brier_calibrated"],
        "ml_calibration_factor": art["ml_calibration_factor"],
        "slices": art["slices"],
        "short": art["short"],
    }, indent=2))


if __name__ == "__main__":
    main()
