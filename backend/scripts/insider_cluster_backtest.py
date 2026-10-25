"""
Insider open-market purchase clusters on the pooled S&P 500 samples, from SEC Form 3/4/5
quarterly data sets (https://www.sec.gov/dera/data/form-345). Point in time: a trade counts
only from its FILING_DATE.

Per (ticker, as_of_date), trailing ``--window`` calendar days of filings:
  n_buyers    — distinct insiders with open-market purchases (code P, acquired)
  buy_usd     — dollar value of those purchases
  net_sellers — distinct insiders with open-market sales (code S) minus n_buyers

    python scripts/insider_cluster_backtest.py --zips /path/to/sec345 --samples .../samples.csv.gz
"""
from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from signals.alpha.score_backtest import rank_ic, summarize_group  # noqa: E402


def load_trades(zdir: Path) -> pd.DataFrame:
    out = []
    for z in sorted(zdir.glob("*_form345.zip")):
        with zipfile.ZipFile(z) as zf:
            rd = lambda n, cols: pd.read_csv(zf.open(n), sep="\t", usecols=cols, dtype=str, quoting=3, on_bad_lines="skip")
            sub = rd("SUBMISSION.tsv", ["ACCESSION_NUMBER", "FILING_DATE", "DOCUMENT_TYPE", "ISSUERTRADINGSYMBOL"])
            tr = rd("NONDERIV_TRANS.tsv", ["ACCESSION_NUMBER", "TRANS_CODE", "TRANS_SHARES", "TRANS_PRICEPERSHARE", "TRANS_ACQUIRED_DISP_CD"])
            own = rd("REPORTINGOWNER.tsv", ["ACCESSION_NUMBER", "RPTOWNERCIK"])
        tr = tr[tr.TRANS_CODE.isin(["P", "S"])]
        own = own.drop_duplicates("ACCESSION_NUMBER")
        m = tr.merge(sub[sub.DOCUMENT_TYPE.isin(["4", "4/A"])], on="ACCESSION_NUMBER").merge(own, on="ACCESSION_NUMBER")
        out.append(m)
        print(z.name, len(m), flush=True)
    d = pd.concat(out, ignore_index=True)
    d["ticker"] = d.ISSUERTRADINGSYMBOL.str.upper().str.strip().str.replace(".", "-", regex=False)
    d["filed"] = pd.to_datetime(d.FILING_DATE, format="%d-%b-%Y", errors="coerce")
    d["usd"] = pd.to_numeric(d.TRANS_SHARES, errors="coerce") * pd.to_numeric(d.TRANS_PRICEPERSHARE, errors="coerce")
    d["buy"] = (d.TRANS_CODE == "P") & (d.TRANS_ACQUIRED_DISP_CD == "A")
    d["sell"] = d.TRANS_CODE == "S"
    return d.dropna(subset=["filed", "ticker"]).drop_duplicates(["ACCESSION_NUMBER", "TRANS_CODE", "TRANS_SHARES", "TRANS_PRICEPERSHARE"])


def features(samples: pd.DataFrame, trades: pd.DataFrame, window: int) -> pd.DataFrame:
    trades = trades[trades.ticker.isin(set(samples.ticker))]
    feats = []
    for t, g in samples.groupby("ticker"):
        tt = trades[trades.ticker == t]
        if tt.empty:
            feats.append(pd.DataFrame({"idx": g.index, "n_buyers": 0, "buy_usd": 0.0, "n_sellers": 0}))
            continue
        rows = []
        for i, d in zip(g.index, g.as_of_date):
            w = tt[(tt.filed <= d) & (tt.filed > d - pd.Timedelta(days=window))]
            b = w[w.buy]
            rows.append((i, b.RPTOWNERCIK.nunique(), float(b.usd.sum()), w[w.sell].RPTOWNERCIK.nunique()))
        feats.append(pd.DataFrame(rows, columns=["idx", "n_buyers", "buy_usd", "n_sellers"]))
    f = pd.concat(feats).set_index("idx")
    out = samples.join(f)
    out["net_buyers"] = out.n_buyers - out.n_sellers
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--zips", required=True)
    ap.add_argument("--samples", default=str(ROOT / "data/alpha/score_backtest/samples.csv.gz"))
    ap.add_argument("--window", type=int, default=90)
    ap.add_argument("--max-date", default=None, help="Last sample date covered by the downloaded quarters")
    ap.add_argument("--step", type=int, default=5)
    ap.add_argument("--cost-pct", type=float, default=0.30)
    args = ap.parse_args()

    s = pd.read_csv(args.samples)
    s["as_of_date"] = pd.to_datetime(s["as_of_date"])
    if args.max_date:
        s = s[s.as_of_date <= pd.Timestamp(args.max_date)]
    tr = load_trades(Path(args.zips))
    print("trades", len(tr), "buys", int(tr.buy.sum()), flush=True)
    m = features(s, tr, args.window)
    m["as_of_date"] = m["as_of_date"].dt.strftime("%Y-%m-%d")
    m["log_buy_usd"] = np.log1p(m.buy_usd)

    rep: dict = {"window_days": args.window, "n": int(len(m)), "ic": {}, "buckets": {}}
    for c in ("n_buyers", "log_buy_usd", "net_buyers"):
        for h in (21, 63, 126):
            rep["ic"][f"{c}_{h}"] = rank_ic(m, c, h, args.step)
    buckets = {
        "no_buyers": m[m.n_buyers == 0],
        "1_buyer": m[m.n_buyers == 1],
        "cluster_2plus": m[m.n_buyers >= 2],
        "cluster_3plus": m[m.n_buyers >= 3],
        "sellers_3plus_no_buys": m[(m.n_sellers >= 3) & (m.n_buyers == 0)],
    }
    for name, g in buckets.items():
        rep["buckets"][name] = {h: summarize_group(g, h, args.step, args.cost_pct) for h in (21, 63, 126)}
    print(json.dumps({k: {kk: (v.get("ic_mean"), v.get("ic_t")) for kk, v in rep["ic"].items()} for k in ["x"]}, default=float))
    for name, d in rep["buckets"].items():
        print(name, {h: (v.get("n"), v.get("net_excess_pct"), v.get("t_stat")) for h, v in d.items()})
    out = Path(args.samples).with_name("insider_ic.json")
    out.write_text(json.dumps(rep, indent=2, default=float))
    print("->", out)


if __name__ == "__main__":
    main()
