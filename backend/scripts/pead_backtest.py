"""
Post-earnings drift on the pooled S&P 500 samples (batch_score_backtest.py output), timed on
announcement dates rather than 10-Q filing dates.

Per (ticker, as_of_date) uses the latest announcement already known by the close:
  surprise_pct — (reported - consensus) / |consensus| from yfinance earnings dates
  ear_3d       — stock minus SPY return from the close before the reaction day to the close
                 after it (after-close reports react next session); known only after that close
  days_since   — calendar days since the announcement became known

    python scripts/pead_backtest.py --samples data/alpha/score_backtest/samples.csv.gz
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import warnings
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore")

from signals.alpha.score_backtest import rank_ic  # noqa: E402


def _earn(t: str, cache: Path) -> pd.DataFrame:
    p = cache / f"{t}.csv"
    if p.exists():
        return pd.read_csv(p)
    import yfinance as yf

    for attempt in range(3):
        try:
            d = yf.Ticker(t).get_earnings_dates(limit=48)
            break
        except Exception:
            d = None
            time.sleep(2 * (attempt + 1))
    if d is None or d.empty:
        out = pd.DataFrame(columns=["ts", "est", "rep"])
    else:
        d = d.dropna(subset=["Reported EPS"])
        out = pd.DataFrame({
            "ts": [str(x) for x in d.index],
            "est": d["EPS Estimate"].to_numpy(),
            "rep": d["Reported EPS"].to_numpy(),
        })
    out.to_csv(p, index=False)
    return out


def events_for(t: str, earn: pd.DataFrame, close: pd.Series, spy: pd.Series) -> pd.DataFrame:
    days = close.dropna().index
    rows = []
    for _, e in earn.iterrows():
        ts = pd.Timestamp(e["ts"])
        local = ts.tz_convert("America/New_York") if ts.tzinfo else ts
        d = pd.Timestamp(local.date())
        after_close = local.hour >= 16 or (local.hour == 0 and local.minute == 0)
        pos = days.searchsorted(d, side="right" if after_close else "left")
        if pos < 1 or pos + 1 >= len(days):
            continue
        r0, r1 = days[pos - 1], days[pos + 1]
        try:
            ear = (close[r1] / close[r0] - 1) - (spy[r1] / spy[r0] - 1)
        except (KeyError, ZeroDivisionError):
            continue
        est, rep = e["est"], e["rep"]
        sp = (rep - est) / abs(est) * 100 if pd.notna(est) and abs(est) > 1e-6 else np.nan
        rows.append({"ticker": t, "known": r1, "surprise_pct": float(np.clip(sp, -100, 100)), "ear_3d": 100 * ear})
    return pd.DataFrame(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--samples", default=str(ROOT / "data/alpha/score_backtest/samples.csv.gz"))
    ap.add_argument("--cache-dir", default=str(ROOT / "data" / "earnings_cache"))
    ap.add_argument("--step", type=int, default=5)
    args = ap.parse_args()
    cache = Path(args.cache_dir)
    cache.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(args.samples)
    df["as_of_date"] = pd.to_datetime(df["as_of_date"])
    tickers = sorted(df.ticker.unique())
    with ThreadPoolExecutor(4) as ex:
        earn = dict(zip(tickers, ex.map(lambda t: _earn(t, cache), tickers)))
    print("earnings fetched", sum(len(v) > 0 for v in earn.values()), "/", len(tickers), flush=True)

    import yfinance as yf

    px = yf.download(tickers + ["SPY"], start="2014-01-01", auto_adjust=True, progress=False, threads=True)["Close"]
    px.index = pd.DatetimeIndex(px.index).tz_localize(None).normalize()
    ev = pd.concat(
        [events_for(t, earn[t], px[t], px["SPY"]) for t in tickers if t in px and len(earn[t])],
        ignore_index=True,
    ).sort_values("known")
    print("events", len(ev), flush=True)

    df = df.sort_values("as_of_date")
    m = pd.merge_asof(df, ev, left_on="as_of_date", right_on="known", by="ticker", direction="backward")
    m["days_since"] = (m["as_of_date"] - m["known"]).dt.days
    m["as_of_date"] = m["as_of_date"].dt.strftime("%Y-%m-%d")
    pct = m.groupby("as_of_date")[["surprise_pct", "ear_3d"]].rank(pct=True)
    m["pead"] = pct.mean(axis=1)

    report: dict = {"n_samples": int(len(m)), "n_events": int(len(ev)), "windows": {}}
    for lo, hi in ((0, 10), (0, 21), (0, 45), (46, 120), (0, 400)):
        s = m[(m.days_since >= lo) & (m.days_since <= hi)]
        report["windows"][f"{lo}-{hi}d"] = {
            "n": int(len(s)),
            **{f"{c}_{h}": rank_ic(s, c, h, args.step) for c in ("surprise_pct", "ear_3d", "pead") for h in (21, 63)},
        }
        print(f"{lo}-{hi}d n={len(s)}", {k: (v.get("ic_mean"), v.get("ic_t")) for k, v in report["windows"][f"{lo}-{hi}d"].items() if k != "n"}, flush=True)
    out = Path(args.samples).with_name("pead_ic.json")
    out.write_text(json.dumps(report, indent=2, default=float))
    m.to_csv(Path(args.samples).with_name("samples_pead.csv.gz"), index=False)
    print("->", out)


if __name__ == "__main__":
    main()
