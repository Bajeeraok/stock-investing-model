"""
Re-test the published predictors that still worked after 2017 in Open Source Asset Pricing
(Chen & Zimmermann, value-weighted decile long-short, t > 2 post-2017) on our pooled S&P 500
samples, with the same overlap-corrected rank IC used for every other factor.

  mom6m          6-month momentum skipping the latest month (OSAP Mom6m)
  mom12m_off     months t-11..t-2 momentum (≈ OSAP Mom12mOffSeason)
  net_buyback    −log(split-adjusted shares / shares one year earlier) (OSAP ShareIss1Y, sign flipped)
  oper_prof      TTM operating income / book equity (OSAP OperProf)
  tax_ratio      TTM income tax expense / TTM net income (OSAP Tax)
  survivor_score mean cross-sectional percentile of the above

    python scripts/survivor_factor_backtest.py --samples .../samples.csv.gz --ohlcv .../ohlcv.pkl --edgar /home/ubuntu/edgar_cache
"""
from __future__ import annotations

import argparse
import json
import sys
import warnings
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore")

from signals.alpha.fundamental_factors import (  # noqa: E402
    _facts_rows, _instant, _known, _quarterly_flow, _ttm, load_cik_map,
)
from signals.alpha.score_backtest import rank_ic  # noqa: E402

FACTORS = ("mom6m", "mom12m_off", "net_buyback", "oper_prof", "tax_ratio")
FLOW = {"oper_inc": ("OperatingIncomeLoss",), "tax": ("IncomeTaxExpenseBenefit",), "ni": ("NetIncomeLoss", "ProfitLoss")}
INST = {"equity": ("StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest")}


def _stitch(facts: dict, aliases, fn) -> pd.DataFrame:
    parts = [fn(r) for c in aliases if (r := _facts_rows(facts, c))]
    if not parts:
        return pd.DataFrame(columns=["end", "val", "filed"])
    return pd.concat(parts, ignore_index=True).drop_duplicates("end", keep="first").sort_values("end").reset_index(drop=True)


def _shares(facts: dict) -> pd.DataFrame:
    u = (((facts.get("facts") or {}).get("dei") or {}).get("EntityCommonStockSharesOutstanding") or {}).get("units") or {}
    rows = [{"end": pd.Timestamp(r["end"]), "val": float(r["val"]), "filed": pd.Timestamp(r["filed"])}
            for r in u.get("shares", []) if r.get("end") and r.get("filed")]
    if not rows:
        return pd.DataFrame(columns=["end", "val", "filed"])
    return pd.DataFrame(rows).sort_values(["end", "filed"]).drop_duplicates("end", keep="first").reset_index(drop=True)


def _acct(args) -> list[dict]:
    t, path, dates, splits = args
    try:
        facts = json.loads(Path(path).read_text())
    except Exception:
        return []
    fl = {k: _stitch(facts, v, _quarterly_flow) for k, v in FLOW.items()}
    eq = _stitch(facts, INST["equity"], _instant)
    sh = _shares(facts)
    sp = pd.Series(splits, dtype=float)
    if len(sp):
        sp.index = pd.to_datetime(sp.index)

    def adj(end: pd.Timestamp, val: float, as_of: pd.Timestamp) -> float:
        # express every share count in units as of `as_of` (multiply by splits after `end`)
        if not len(sp):
            return val
        f = sp[(sp.index > end) & (sp.index <= as_of)]
        return val * float(f.prod()) if len(f) else val

    out = []
    for d in dates:
        a = pd.Timestamp(d)
        row = {"ticker": t, "as_of_date": d, "net_buyback": None, "oper_prof": None, "tax_ratio": None}
        k = _known(sh, a)
        if len(k) >= 2:
            last = k.iloc[-1]
            prev = k[(k.end <= last.end - pd.Timedelta(days=330)) & (k.end >= last.end - pd.Timedelta(days=400))]
            if len(prev) and (last.end - a).days > -200:
                s1, s0 = adj(last.end, last.val, a), adj(prev.end.iloc[-1], prev.val.iloc[-1], a)
                if s1 > 0 and s0 > 0:
                    row["net_buyback"] = -float(np.log(s1 / s0))
        oi, e = _ttm(_known(fl["oper_inc"], a)), _known(eq, a)
        if oi is not None and len(e) and e.val.iloc[-1] > 0:
            row["oper_prof"] = oi / float(e.val.iloc[-1])
        tx, ni = _ttm(_known(fl["tax"], a)), _ttm(_known(fl["ni"], a))
        if tx is not None and ni is not None and ni > 0:
            row["tax_ratio"] = tx / ni
        out.append(row)
    return out


def _splits(t: str) -> dict:
    import yfinance as yf

    try:
        s = yf.Ticker(t).splits
        return {str(k.date()): float(v) for k, v in s.items() if v and v > 0}
    except Exception:
        return {}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--samples", default=str(ROOT / "data/alpha/score_backtest/samples.csv.gz"))
    ap.add_argument("--ohlcv", required=True)
    ap.add_argument("--edgar", default=str(ROOT / "data" / "edgar_cache"))
    ap.add_argument("--step", type=int, default=5)
    args = ap.parse_args()

    df = pd.read_csv(args.samples)
    close = pd.read_pickle(args.ohlcv)["Close"]
    c = close.reindex(columns=sorted(set(df.ticker) & set(close.columns)))
    mom6 = c.shift(21) / c.shift(126) - 1
    mom12o = c.shift(42) / c.shift(252) - 1
    for name, m in (("mom6m", mom6), ("mom12m_off", mom12o)):
        s = m.stack().rename(name).reset_index()
        s.columns = ["date", "ticker", name]
        s["as_of_date"] = s.date.dt.strftime("%Y-%m-%d")
        df = df.merge(s[["ticker", "as_of_date", name]], on=["ticker", "as_of_date"], how="left")

    cache = Path(args.edgar)
    sp_path = Path(args.samples).with_name("splits.json")
    tickers = sorted(df.ticker.unique())
    if sp_path.exists():
        splits = json.loads(sp_path.read_text())
    else:
        with ThreadPoolExecutor(8) as ex:
            splits = dict(zip(tickers, ex.map(_splits, tickers)))
        sp_path.write_text(json.dumps(splits))
    ciks = load_cik_map(cache)
    by_t = df.groupby("ticker")["as_of_date"].apply(lambda s: sorted(set(s))).to_dict()
    jobs = []
    for t in tickers:
        cik = ciks.get(t.upper().replace("-", "."))
        p = cache / f"CIK{cik:010d}.json" if cik else None
        if p is not None and p.exists():
            jobs.append((t, str(p), by_t[t], splits.get(t, {})))
    rows = []
    with ProcessPoolExecutor(6) as ex:
        for out in ex.map(_acct, jobs, chunksize=4):
            rows.extend(out)
    df = df.merge(pd.DataFrame(rows), on=["ticker", "as_of_date"], how="left")
    pct = df.groupby("as_of_date")[list(FACTORS)].rank(pct=True)
    df["survivor_score"] = pct.mean(axis=1).where(pct.notna().sum(axis=1) >= 3)
    cols = (*FACTORS, "survivor_score")
    df["year"] = df.as_of_date.str[:4]
    rep: dict = {"n": int(len(df)), "coverage_pct": {k: round(100 * float(df[k].notna().mean()), 1) for k in cols}, "horizons": {}}
    for h in (21, 63, 126):
        rep["horizons"][str(h)] = {k: rank_ic(df, k, h, args.step) for k in cols}
    rep["survivor_ic_by_year_63"] = {y: rank_ic(g, "survivor_score", 63, args.step).get("ic_mean") for y, g in df.groupby("year")}
    out = Path(args.samples).with_name("survivor_ic.json")
    out.write_text(json.dumps(rep, indent=2, default=float))
    df.to_csv(Path(args.samples).with_name("samples_survivor.csv.gz"), index=False)
    print(json.dumps(rep["coverage_pct"]))
    for h, r in rep["horizons"].items():
        print(h, {k: (round(v.get("ic_mean") or 0, 4), round(v.get("ic_t") or 0, 2)) for k, v in r.items()})
    print(rep["survivor_ic_by_year_63"])


if __name__ == "__main__":
    main()
