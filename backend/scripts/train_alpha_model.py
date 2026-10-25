"""
Train the pooled cross-sectional alpha model (signals/alpha/pooled_model.py).

Downloads daily OHLCV with yfinance for S&P 500 members (survivorship-aware membership
mask), SPY and sector ETFs; builds relative features and excess / triple-barrier labels;
runs purged walk-forward + locked holdout; writes data/alpha/pooled_model.pkl and a JSON
metrics report. Only promoted horizons are used by the live app.

    cd backend && python scripts/train_alpha_model.py --max-tickers 200 --years 12
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from signals.alpha.features import SECTOR_ETF, build_panel
from signals.alpha.labels import excess_label, forward_excess_return, forward_return, triple_barrier_label
from signals.alpha.pooled_model import HORIZONS, WalkForwardConfig, save_artifact, train_all
from signals.alpha.universe import DEFAULT_MEMBERSHIP_CSV, load_membership, membership_mask, sector_map


def download(tickers: list[str], years: int) -> dict[str, pd.DataFrame]:
    import yfinance as yf

    raw = yf.download(tickers, period=f"{years}y", auto_adjust=True, group_by="ticker", progress=False, threads=True)
    out = {}
    for t in tickers:
        try:
            d = raw[t].rename(columns=str.lower).dropna(subset=["close"])
        except KeyError:
            continue
        if len(d) > 300:
            d.index = pd.to_datetime(d.index).tz_localize(None)
            out[t] = d
    return out


def make_labels(cost: float):
    def fn(tk: str, df: pd.DataFrame, bclose: pd.Series) -> pd.DataFrame:
        c = df["close"].astype(float)
        cols = {}
        for h, n in HORIZONS.items():
            cols[f"y_beat_{h}"] = excess_label(c, bclose, n, cost)
            cols[f"y_tb_{h}"] = triple_barrier_label(c, df["high"], df["low"], n)
            cols[f"fwd_ret_{h}"] = forward_return(c, n)
            cols[f"fwd_exc_{h}"] = forward_excess_return(c, bclose, n)
        return pd.DataFrame(cols, index=df.index)

    return fn


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--membership", default=str(DEFAULT_MEMBERSHIP_CSV))
    ap.add_argument("--max-tickers", type=int, default=200)
    ap.add_argument("--years", type=int, default=12)
    ap.add_argument("--cost", type=float, default=0.003)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    mem = load_membership(args.membership)
    start = pd.Timestamp.today() - pd.DateOffset(years=args.years)
    eligible = mem[mem["end_date"].isna() | (mem["end_date"] >= start)]
    tickers = sorted(eligible["ticker"].unique())[: args.max_tickers] if args.max_tickers else sorted(eligible["ticker"].unique())
    data = download(tickers + ["SPY"] + list(SECTOR_ETF.values()), args.years)
    print(f"downloaded {len(data)} series")
    panel = build_panel(data, sector_of=sector_map(mem), extra_label_fn=make_labels(args.cost))
    panel = panel[membership_mask(panel, mem)]
    print(f"panel rows {len(panel):,}, tickers {panel.index.get_level_values('ticker').nunique()}")
    cfg = WalkForwardConfig(cost=args.cost)
    art = train_all(panel, cfg)
    art["universe"] = {"n_tickers": int(panel.index.get_level_values("ticker").nunique()), "years": args.years}
    p = save_artifact(art, args.out)
    report = {
        h: {k: v for k, v in hm.items() if k not in ("models", "calibrators", "quantile_models", "features")}
        for h, hm in art["horizons"].items()
    }
    report["universe"] = art["universe"]
    Path(p).with_suffix(".json").write_text(json.dumps(report, indent=2, default=str))
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
