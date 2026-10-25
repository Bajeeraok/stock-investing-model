"""
Point-in-time EDGAR fundamental factors on the pooled S&P 500 samples from
batch_score_backtest.py: rank IC per factor + fund_score bucket table vs SPY.

    python scripts/fundamental_factor_backtest.py --samples data/alpha/score_backtest/samples.csv.gz
Writes ``fundamental_ic.json`` next to the samples file.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import warnings
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore")

from signals.alpha.fundamental_factors import (  # noqa: E402
    FACTORS,
    SEC_UA,
    add_fund_score,
    factors_as_of,
    fetch_companyfacts,
    load_cik_map,
    parse_companyfacts,
)
from signals.alpha.score_backtest import bucket_of, bucket_table, rank_ic  # noqa: E402

CACHE = ROOT / "data" / "edgar_cache"


def _ticker_factors(args: tuple[str, str, list[str]]) -> list[dict]:
    ticker, path, dates = args
    try:
        parsed = parse_companyfacts(json.loads(Path(path).read_text()))
    except Exception:
        return []
    rows = []
    for d in dates:
        f = factors_as_of(parsed, d)
        f.update(ticker=ticker, as_of_date=d)
        rows.append(f)
    return rows


IC_MIN, T_MIN = 0.02, 2.0


def validate(report: dict) -> dict:
    """fund_score is promoted (opens the satellite) only with IC >= 0.02 and corrected t >= 2 at 21d or 63d."""
    passing = {
        h: r["ic"]["fund_score"]
        for h, r in report["horizons"].items()
        if h in ("21", "63")
        and (r["ic"]["fund_score"].get("ic_mean") or 0) >= IC_MIN
        and (r["ic"]["fund_score"].get("ic_t") or 0) >= T_MIN
    }
    return {
        "validated": bool(passing),
        "rule": f"fund_score rank IC >= {IC_MIN} and overlap-corrected t >= {T_MIN} at 21d or 63d",
        "fund_score_ic": {h: report["horizons"][h]["ic"]["fund_score"] for h in report["horizons"]},
        "passing_horizons": sorted(passing),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--samples", default=str(ROOT / "data/alpha/score_backtest/samples.csv.gz"))
    ap.add_argument("--cache-dir", default=str(CACHE))
    ap.add_argument("--user-agent", default=SEC_UA)
    ap.add_argument("--step", type=int, default=5)
    ap.add_argument("--cost", type=float, default=0.003)
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    cache = Path(args.cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(args.samples)
    ciks = load_cik_map(cache, args.user_agent)
    by_t = df.groupby("ticker")["as_of_date"].apply(lambda s: sorted(set(s))).to_dict()

    jobs, missing = [], []
    for i, t in enumerate(sorted(by_t)):
        cik = ciks.get(t.upper().replace("-", "."))
        if cik is None:
            missing.append(t)
            continue
        p = cache / f"CIK{cik:010d}.json"
        fresh = p.exists()
        if fetch_companyfacts(cik, cache, args.user_agent, max_age_days=30) is None:
            missing.append(t)
            continue
        if not fresh:
            time.sleep(0.12)  # SEC fair-access: <= 10 req/s
        jobs.append((t, str(p), by_t[t]))
        if (i + 1) % 50 == 0:
            print(f"{i + 1}/{len(by_t)} facts, {len(missing)} missing", flush=True)
    print(f"facts for {len(jobs)} tickers; no CIK/facts: {len(missing)}", flush=True)

    rows: list[dict] = []
    with ProcessPoolExecutor(args.workers) as ex:
        for out in ex.map(_ticker_factors, jobs, chunksize=4):
            rows.extend(out)
    fac = pd.DataFrame(rows)
    df = df.merge(fac, on=["ticker", "as_of_date"], how="left")
    df = add_fund_score(df)

    report: dict = {
        "n_samples": int(len(df)),
        "n_tickers_with_facts": len(jobs),
        "coverage_pct": {c: round(100 * float(df[c].notna().mean()), 1) for c in (*FACTORS, "fund_score")},
        "missing_tickers": missing,
        "horizons": {},
    }
    fs = df.dropna(subset=["fund_score"]).copy()
    fs["score"] = fs["fund_score"]
    fs["bucket"] = fs["score"].map(bucket_of)
    fs["year"] = fs["as_of_date"].str[:4]
    for h in (21, 63, 126):
        report["horizons"][str(h)] = {
            "ic": {c: rank_ic(df, c, h, args.step) for c in ("score", *FACTORS, "fund_score")},
            "fund_score_buckets": bucket_table(fs, h, args.step, args.cost),
            "fund_score_ic_by_year": {y: rank_ic(g, "fund_score", h, args.step) for y, g in fs.groupby("year")},
        }
    report["validation"] = validate(report)
    (ROOT / "data" / "alpha" / "fundamental_validation.json").write_text(json.dumps(report["validation"], indent=2))
    out = Path(args.samples).with_name("fundamental_ic.json")
    out.write_text(json.dumps(report, indent=2, default=float))
    df.to_csv(Path(args.samples).with_name("samples_fundamental.csv.gz"), index=False)
    for h, r in report["horizons"].items():
        print(h, {k: (v.get("ic_mean"), v.get("ic_t")) for k, v in r["ic"].items()})
    print("->", out)


if __name__ == "__main__":
    main()
