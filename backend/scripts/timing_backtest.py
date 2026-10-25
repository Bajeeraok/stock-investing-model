"""
Same-stock timing backtest: does the app's entry-band / signal timing beat simply owning the
stock? (Selection vs SPY is a different question — see batch_score_backtest.py.)

Uses the live entry-zone functions (compute_short_term_entry / compute_medium_term_entry via
entry_band_touch._inputs_at_bar) on each pooled S&P 500 sample date.

  A. band position -> forward return minus the same stock's average forward return that year
  B. "wait for pullback": when spot is above the zone, limit at the zone top for 20 sessions
     (else buy at day 20) vs buying now; both marked at day 63
  C. signal-following per stock (exit score<=35, re-enter >=65; SPY 200d regime; both) vs
     buy-and-hold the same stock

    python scripts/timing_backtest.py --samples .../samples.csv.gz --ohlcv .../ohlcv.pkl
"""
from __future__ import annotations

import argparse
import json
import sys
import warnings
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore")

WAIT, MARK = 20, 63
LOOKBACK = 400
EXAMPLES = ("AAPL", "MSFT", "NVDA", "AMZN", "JPM", "XOM", "JNJ", "CAT", "NEE", "PG", "GOOGL", "LIN", "PLD", "META", "T")
_PX: dict = {}


def _init(ohlcv_path: str) -> None:
    _PX["df"] = pd.read_pickle(ohlcv_path)


def _frame(t: str) -> pd.DataFrame | None:
    px = _PX["df"]
    try:
        f = pd.DataFrame({k.lower(): px[k][t] for k in ("Open", "High", "Low", "Close", "Volume")}).dropna()
    except KeyError:
        return None
    return f if len(f) > 300 else None


def _zones(args) -> list[dict]:
    t, dates = args
    from signals.entry_band_touch import _inputs_at_bar
    from signals.horizon_entry_calculator import (
        MediumTermInputs, ShortTermInputs, compute_medium_term_entry, compute_short_term_entry,
    )
    from signals.volatility import atr_series_wilder

    f = _frame(t)
    if f is None:
        return []
    close = f["close"]
    atr = atr_series_wilder(f["high"], f["low"], close, window=14)
    pos_of = {d: i for i, d in enumerate(close.index)}
    lows, opens = f["low"].to_numpy(), f["open"].to_numpy()
    c = close.to_numpy()
    out = []
    for d in dates:
        i = pos_of.get(pd.Timestamp(d))
        if i is None or i < 200:
            continue
        try:
            lo = max(0, i - LOOKBACK + 1)  # live indicators re-walk full history; 400 bars covers MA200/52w
            inp = _inputs_at_bar(close.iloc[lo : i + 1], i - lo, ohlcv_df=f.iloc[lo : i + 1], atr_series=atr.iloc[lo : i + 1])
            if not inp:
                continue
            p = inp["price"]
            st = compute_short_term_entry(ShortTermInputs(
                current_price=p, ml_prob=inp["ml_prob"], rsi=inp["rsi"], atr=inp["atr"], vwap=inp["vwap"],
                support_level=inp["support"], resistance_level=inp["resistance"],
                regime_bull_pct=inp["regime_bull_pct"], pattern_score=inp["pattern_score"],
                volume_ratio=inp["volume_ratio"]))
            mt = compute_medium_term_entry(MediumTermInputs(
                current_price=p, ml_prob=inp["ml_prob"], ma50=inp["ma50"], ma200=inp["ma200"], atr=inp["atr"],
                regime_bull_pct=inp["regime_bull_pct"], pattern_score=inp["pattern_score"],
                days_to_earnings=None, options_sentiment_score=50.0, insider_activity_score=50.0,
                fundamentals_score=50.0, short_entry_low=st.entry_zone.low, short_entry_high=st.entry_zone.high))
        except Exception:
            continue
        row = {"ticker": t, "as_of_date": str(pd.Timestamp(d).date())}
        for k, z in (("st", st.entry_zone), ("mt", mt.entry_zone)):
            el, eh = float(z.low), float(z.high)
            row[f"{k}_pos"] = "inside" if el <= p <= eh * 1.0001 else ("above" if p > eh else "below")
            if row[f"{k}_pos"] == "above" and i + MARK < len(c):
                fill = None
                for j in range(i + 1, i + WAIT + 1):
                    if lows[j] <= eh:
                        fill = min(eh, opens[j])
                        break
                filled = fill is not None
                fill = fill if filled else c[i + WAIT]
                row[f"{k}_wait_gain"] = 100 * (c[i] / fill - 1)
                row[f"{k}_wait_filled"] = filled
        out.append(row)
    return out


def _metrics(r: pd.Series) -> dict:
    r = r.fillna(0.0)
    if len(r) < 60:
        return {}
    eq = (1 + r).cumprod()
    yrs = len(r) / 252
    vol = r.std() * np.sqrt(252)
    return {
        "cagr": 100 * (eq.iloc[-1] ** (1 / yrs) - 1),
        "sharpe": (r.mean() * 252 / vol) if vol > 0 else np.nan,
        "max_dd": 100 * float((eq / eq.cummax() - 1).min()),
    }


def follow(samples: pd.DataFrame, cost: float) -> dict:
    px = _PX["df"]["Close"]
    spy = px["SPY"].dropna()
    from signals.alpha.core_satellite import regime_series

    reg = regime_series(spy, 200, 1.0)
    per, port = [], {k: [] for k in ("buy_hold", "score", "regime", "score_regime")}
    for t, g in samples.groupby("ticker"):
        if t not in px:
            continue
        cl = px[t].dropna()
        g = g.sort_values("as_of_date")
        d0, d1 = pd.Timestamp(g.as_of_date.iloc[0]), pd.Timestamp(g.as_of_date.iloc[-1])
        cl = cl.loc[d0:d1]
        if len(cl) < 252:
            continue
        ret = cl.pct_change().fillna(0.0)
        sc = g.set_index(pd.to_datetime(g.as_of_date))["score"].reindex(cl.index)
        state, s_pos = 1.0, []
        for v in sc.to_numpy():
            if v == v:
                state = 0.0 if v <= 35 else (1.0 if v >= 65 else state)
            s_pos.append(state)
        s_pos = pd.Series(s_pos, index=cl.index)
        r_pos = reg.reindex(cl.index).ffill().fillna(1.0)
        pos = {"buy_hold": pd.Series(1.0, index=cl.index), "score": s_pos, "regime": r_pos, "score_regime": s_pos * r_pos}
        row = {"ticker": t}
        for k, w in pos.items():
            w = w.shift(1).fillna(1.0)
            strat = w * ret - w.diff().abs().fillna(0.0) * cost
            port[k].append(strat.rename(t))
            for m, v in _metrics(strat).items():
                row[f"{k}_{m}"] = v
            row[f"{k}_in_mkt"] = 100 * float(w.mean())
        per.append(row)
    per = pd.DataFrame(per)
    rep: dict = {"n_stocks": int(len(per)), "median": {}, "pct_stocks_better_than_buy_hold": {}, "equal_weight_portfolio": {}}
    for k in port:
        rep["median"][k] = {m: round(float(per[f"{k}_{m}"].median()), 3) for m in ("cagr", "sharpe", "max_dd", "in_mkt")}
        if k != "buy_hold":
            rep["pct_stocks_better_than_buy_hold"][k] = {
                "cagr": round(100 * float((per[f"{k}_cagr"] > per["buy_hold_cagr"]).mean()), 1),
                "sharpe": round(100 * float((per[f"{k}_sharpe"] > per["buy_hold_sharpe"]).mean()), 1),
                "smaller_drawdown": round(100 * float((per[f"{k}_max_dd"] > per["buy_hold_max_dd"]).mean()), 1),
            }
        ew = pd.concat(port[k], axis=1).mean(axis=1)
        rep["equal_weight_portfolio"][k] = {m: round(float(v), 3) for m, v in _metrics(ew).items()}
    ex = per[per.ticker.isin(EXAMPLES)].set_index("ticker").round(2)
    rep["examples"] = ex.to_dict(orient="index")
    rep["_per_stock"] = per
    return rep


def main() -> None:
    from signals.alpha.score_backtest import summarize_group

    ap = argparse.ArgumentParser()
    ap.add_argument("--samples", default=str(ROOT / "data/alpha/score_backtest/samples.csv.gz"))
    ap.add_argument("--ohlcv", required=True)
    ap.add_argument("--max-tickers", type=int, default=0)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--cost-pct", type=float, default=0.30)
    args = ap.parse_args()

    s = pd.read_csv(args.samples)
    tickers = sorted(s.ticker.unique())
    if args.max_tickers:
        tickers = tickers[: args.max_tickers]
        s = s[s.ticker.isin(tickers)]
    jobs = [(t, g.as_of_date.tolist()) for t, g in s.groupby("ticker")]
    with Pool(args.workers, initializer=_init, initargs=(args.ohlcv,)) as pool:
        z = pd.DataFrame([r for rows in pool.imap_unordered(_zones, jobs, chunksize=4) for r in rows])
    m = s.merge(z, on=["ticker", "as_of_date"])
    m["year"] = m.as_of_date.str[:4]
    rep: dict = {"n": int(len(m)), "band_position": {}, "wait_for_pullback": {}}
    for h in (21, 63, 126):
        m[f"timing_{h}"] = m[f"ret_{h}"] - m.groupby(["ticker", "year"])[f"ret_{h}"].transform("mean")
    for k in ("st", "mt"):
        rep["band_position"][k] = {}
        for pos, g in m.groupby(f"{k}_pos"):
            rep["band_position"][k][pos] = {"share_pct": round(100 * len(g) / len(m), 1)}
            for h in (21, 63, 126):
                gg = g[["as_of_date", f"timing_{h}"]].rename(columns={f"timing_{h}": f"excess_{h}"})
                r = summarize_group(gg, h, 5, 0.0)
                rep["band_position"][k][pos][h] = {x: r.get(x) for x in ("n", "mean_excess_pct", "t_stat", "n_eff")}
        w = m.dropna(subset=[f"{k}_wait_gain"]) if f"{k}_wait_gain" in m else m.iloc[:0]
        if len(w):
            gg = w[["as_of_date", f"{k}_wait_gain"]].rename(columns={f"{k}_wait_gain": "excess_63"})
            r = summarize_group(gg, MARK, 5, 0.0)
            rep["wait_for_pullback"][k] = {
                "n": int(len(w)), "fill_rate_pct": round(100 * float(w[f"{k}_wait_filled"].mean()), 1),
                "mean_gain_vs_buy_now_pct": r.get("mean_excess_pct"), "t_stat": r.get("t_stat"),
                "pct_cases_better": round(100 * float((w[f"{k}_wait_gain"] > 0).mean()), 1),
            }
    _init(args.ohlcv)
    rep["signal_following"] = follow(s, args.cost_pct / 100 / 2)
    rep["signal_following"].pop("_per_stock").to_csv(Path(args.samples).with_name("timing_per_stock.csv"), index=False)
    out = Path(args.samples).with_name("timing_backtest.json")
    out.write_text(json.dumps(rep, indent=2, default=float))
    print(json.dumps(rep, indent=1, default=float))


if __name__ == "__main__":
    main()
