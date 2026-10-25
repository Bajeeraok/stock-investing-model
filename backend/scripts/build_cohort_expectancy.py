"""
Build data/alpha/cohort_expectancy.json — measured excess return vs SPY per signal cohort.

Reads local EOD snapshots, or downloads them first from a running deployment with
--api-url (GET /api/eod/snapshots and /api/eod/snapshots/{date}). Each (date, ticker) row becomes one observation
with ticker forward return minus benchmark forward return over --forward-days snapshot steps.
The artifact drives the "Prefer SPY" verdict and measured-expectancy position sizing.

    cd backend && python scripts/build_cohort_expectancy.py
    cd backend && python scripts/build_cohort_expectancy.py --forward-days 21 --cost-pct 0.30
    cd backend && python scripts/build_cohort_expectancy.py --api-url https://thrive-alpha.up.railway.app \
        --eod-dir /tmp/eod_prod --forward-days 21
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.generate_validation_dataset import _closes_by_ticker, _forward_return, _load_snapshots
from signals.alpha.excess import (
    DEFAULT_ARTIFACT_PATH,
    build_cohort_expectancy,
    excess_return_pct,
    save_artifact,
)


def records_from_snapshots(snaps: dict[str, dict], benchmark: str, forward_days: int) -> list[dict]:
    dates = sorted(snaps)
    closes = _closes_by_ticker(snaps)
    bench = closes.get(benchmark.upper(), {})
    out: list[dict] = []
    for i, d in enumerate(dates):
        later = dates[i + 1:]
        b = _forward_return(bench, d, [x for x in later if x in bench], forward_days)
        if b is None:
            continue
        for row in snaps[d].get("run_results") or []:
            t = str(row.get("ticker") or "").upper()
            if not t or t == benchmark.upper():
                continue
            tc = closes.get(t, {})
            f = _forward_return(tc, d, [x for x in later if x in tc], forward_days)
            if f is None:
                continue
            out.append(
                {
                    "as_of_date": d,
                    "ticker": t,
                    "horizon_days": forward_days,
                    "composite_buy": row.get("composite_buy"),
                    "entry_mode": row.get("entry_mode")
                    or (row.get("retail_status") or {}).get("entry_mode")
                    or (row.get("retail_action") or {}).get("entry_mode"),
                    "actual_return_pct": f,
                    "benchmark_return_pct": b,
                    "excess_return_pct": excess_return_pct(f, b),
                }
            )
    return out


def download_snapshots(api_url: str, eod_dir: Path, *, refresh: bool = False, timeout: int = 60) -> int:
    """Mirror a deployment's EOD snapshots into ``eod_dir``; returns how many files were written."""
    base = api_url.rstrip("/")
    idx = requests.get(f"{base}/api/eod/snapshots", timeout=timeout)
    idx.raise_for_status()
    eod_dir.mkdir(parents=True, exist_ok=True)
    wrote = 0
    for s in idx.json().get("snapshots") or []:
        d = s.get("date")
        dest = eod_dir / f"{d}.json"
        if not d or (dest.exists() and not refresh):
            continue
        r = requests.get(f"{base}/api/eod/snapshots/{d}", timeout=timeout)
        if r.status_code != 200:
            print(f"skip {d}: HTTP {r.status_code}")
            continue
        body = r.json()
        snap = body.get("snapshot") if isinstance(body.get("snapshot"), dict) else body
        dest.write_text(json.dumps(snap), encoding="utf-8")
        wrote += 1
    return wrote


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--eod-dir", default="data/eod")
    ap.add_argument("--benchmark", default="SPY")
    ap.add_argument("--forward-days", type=int, default=20)
    ap.add_argument("--cost-pct", type=float, default=0.30, help="Round-trip cost in percent")
    ap.add_argument("--prior-n", type=float, default=30.0, help="Shrinkage pseudo-count toward 0 excess")
    ap.add_argument("--out", default=str(DEFAULT_ARTIFACT_PATH))
    ap.add_argument("--api-url", default=None, help="Download snapshots from this deployment into --eod-dir first")
    ap.add_argument("--refresh", action="store_true", help="With --api-url, re-download existing dates")
    args = ap.parse_args()

    eod_dir = Path(args.eod_dir)
    if not eod_dir.is_absolute():
        eod_dir = ROOT / eod_dir
    if args.api_url:
        print(f"downloaded {download_snapshots(args.api_url, eod_dir, refresh=args.refresh)} snapshots -> {eod_dir}")
    recs = records_from_snapshots(_load_snapshots(eod_dir), args.benchmark, args.forward_days)
    art = build_cohort_expectancy(
        recs,
        horizon_days=args.forward_days,
        cost_pct=args.cost_pct,
        prior_n=args.prior_n,
        benchmark=args.benchmark.upper(),
    )
    art["n_records"] = len(recs)
    path = save_artifact(art, args.out)
    print(f"{len(recs)} observations -> {path}")
    print(json.dumps({k: v for k, v in art["cohorts"].items() if v.get("n", 0) >= 30}, indent=1)[:4000])


if __name__ == "__main__":
    main()
