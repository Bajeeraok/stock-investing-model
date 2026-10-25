"""
Rank IC of textbook price factors on the same pooled samples as batch_score_backtest.py,
so the composite score can be judged against simple, documented baselines.

    python scripts/factor_baseline_ic.py --samples data/alpha/score_backtest/samples.csv.gz
"""
from __future__ import annotations

import argparse
import json
import sys
import warnings
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore")

FACTORS = ("mom_12_1", "mom_6_1", "rev_1m", "low_vol_63", "near_52w_high")


def _factors(ticker: str, dates: list[str]) -> list[dict]:
    from signals.fetcher import fetch_ohlcv_safe

    try:
        close = fetch_ohlcv_safe(ticker, "10y")
    except Exception:
        return []
    if close is None or len(close) < 260:
        return []
    close = close.copy()
    close.index = pd.DatetimeIndex(close.index).tz_localize(None).normalize()
    ret = close.pct_change()
    f = pd.DataFrame({
        "mom_12_1": close.shift(21) / close.shift(252) - 1,
        "mom_6_1": close.shift(21) / close.shift(126) - 1,
        "rev_1m": -(close / close.shift(21) - 1),
        "low_vol_63": -ret.rolling(63).std(),
        "near_52w_high": close / close.rolling(252).max(),
    })
    f = f.reindex(pd.to_datetime(dates)).dropna(how="all")
    f["as_of_date"] = f.index.strftime("%Y-%m-%d")
    f["ticker"] = ticker
    return f.to_dict("records")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--samples", default=str(ROOT / "data/alpha/score_backtest/samples.csv.gz"))
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--step", type=int, default=5, help="Sampling step used by batch_score_backtest.py")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    from signals.alpha.score_backtest import rank_ic

    df = pd.read_csv(args.samples)
    step = args.step
    by_t = df.groupby("ticker")["as_of_date"].apply(list).to_dict()
    rows: list[dict] = []
    with ProcessPoolExecutor(args.workers) as ex:
        for out in ex.map(_factors, list(by_t), list(by_t.values()), chunksize=8):
            rows.extend(out)
    df = df.merge(pd.DataFrame(rows), on=["as_of_date", "ticker"], how="left")
    report = {}
    for h in (21, 63, 126):
        report[str(h)] = {c: rank_ic(df, c, h, step) for c in ("score", "score_raw", *FACTORS)}
    out = Path(args.out) if args.out else Path(args.samples).with_name("factor_ic.json")
    out.write_text(json.dumps(report, indent=2, default=float))
    for h, r in report.items():
        print(h, {k: (v.get("ic_mean"), v.get("ic_t")) for k, v in r.items()})


if __name__ == "__main__":
    main()
