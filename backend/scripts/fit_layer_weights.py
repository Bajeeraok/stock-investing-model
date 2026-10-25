"""
Fit confidence-layer weights from tracked outcomes (signals/alpha/stacker.py).

Input: JSONL rows with layer scores (``layer_scores`` or ``confidence_breakdown``), a
``horizon`` key (short/medium/long, default short) and ``excess_return_pct``.
Writes data/alpha/learned_layer_weights.json; confidence_engine uses a horizon's
learned weights only when they beat the hand-set weights out of sample.

    cd backend && python scripts/fit_layer_weights.py --rows data/alpha/layer_outcomes.jsonl
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from signals.alpha.stacker import fit_layer_weights, save_weights
from signals.confidence_engine import _HORIZON_WEIGHTS


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", required=True)
    ap.add_argument("--min-n", type=int, default=200)
    args = ap.parse_args()
    by_h: dict[str, list[dict]] = defaultdict(list)
    for line in Path(args.rows).read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            by_h[str(r.get("horizon") or "short")].append(r)
    res = {h: fit_layer_weights(rows, _HORIZON_WEIGHTS.get(h, {}), min_n=args.min_n) for h, rows in by_h.items()}
    print(json.dumps(res, indent=2))
    print(save_weights(res))


if __name__ == "__main__":
    main()
