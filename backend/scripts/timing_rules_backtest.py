"""
Candidate same-stock hold/exit/sizing rules vs buy-and-hold of the same stock
(S&P 500 pooled, membership span from the score-backtest samples). Decisions at close t,
applied from t+1; cash earns 13-week T-bill (^IRX); cost per unit of weight change.

    python scripts/timing_rules_backtest.py --samples .../samples.csv.gz --ohlcv .../ohlcv.pkl
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

EXAMPLES = ("AAPL", "MSFT", "NVDA", "AMZN", "JPM", "XOM", "JNJ", "CAT", "NEE", "PG", "GOOGL", "LIN", "PLD", "META", "T")


def _hysteresis(above: np.ndarray, below: np.ndarray) -> np.ndarray:
    out, cur = np.ones(len(above)), 1.0
    for i in range(len(above)):
        if above[i]:
            cur = 1.0
        elif below[i]:
            cur = 0.0
        out[i] = cur
    return out


def trend_sma(c: pd.Series, n: int = 200, band: float = 0.01) -> pd.Series:
    sma = c.rolling(n).mean()
    w = _hysteresis((c > sma * (1 + band)).to_numpy(), (c < sma * (1 - band)).to_numpy())
    return pd.Series(np.where(sma.isna(), 1.0, w), index=c.index)


def golden_cross(c: pd.Series) -> pd.Series:
    s50, s200 = c.rolling(50).mean(), c.rolling(200).mean()
    return pd.Series(np.where(s200.isna() | (s50 >= s200), 1.0, 0.0), index=c.index)


def momentum(c: pd.Series, n: int = 252) -> pd.Series:
    m = c / c.shift(n) - 1
    return pd.Series(np.where(m.isna() | (m > 0), 1.0, 0.0), index=c.index)


def chandelier(c: pd.Series, atr: pd.Series, k: float = 3.0, reentry: int = 50) -> pd.Series:
    """Exit when close < peak-since-entry − k·ATR; re-enter on a new `reentry`-day closing high."""
    cv, av = c.to_numpy(), atr.to_numpy()
    hi = c.rolling(reentry).max().to_numpy()
    w, inn, peak = np.ones(len(c)), True, cv[0]
    for i in range(len(c)):
        if inn:
            peak = max(peak, cv[i])
            if av[i] == av[i] and cv[i] < peak - k * av[i]:
                inn = False
        elif cv[i] >= hi[i]:
            inn, peak = True, cv[i]
        w[i] = 1.0 if inn else 0.0
    return pd.Series(w, index=c.index)


def pct_stop(c: pd.Series, dd: float = 0.20, reentry: int = 50) -> pd.Series:
    cv = c.to_numpy()
    hi = c.rolling(reentry).max().to_numpy()
    w, inn, peak = np.ones(len(c)), True, cv[0]
    for i in range(len(c)):
        if inn:
            peak = max(peak, cv[i])
            if cv[i] < peak * (1 - dd):
                inn = False
        elif cv[i] >= hi[i]:
            inn, peak = True, cv[i]
        w[i] = 1.0 if inn else 0.0
    return pd.Series(w, index=c.index)


def vol_target(c: pd.Series) -> pd.Series:
    """Scale to the stock's own expanding median 63d vol (point-in-time), capped at 1 (no leverage)."""
    v = c.pct_change().rolling(63).std()
    tgt = v.expanding(126).median()
    return (tgt / v).clip(upper=1.0).fillna(1.0)


def _metrics(r: pd.Series, rf: pd.Series) -> dict:
    if len(r) < 120:
        return {}
    eq = (1 + r).cumprod()
    yrs = len(r) / 252
    ex = r - rf
    vol = ex.std() * np.sqrt(252)
    return {
        "cagr": 100 * (eq.iloc[-1] ** (1 / yrs) - 1),
        "sharpe": ex.mean() * 252 / vol if vol > 0 else np.nan,
        "max_dd": 100 * float((eq / eq.cummax() - 1).min()),
    }


def main() -> None:
    from signals.alpha.core_satellite import regime_series

    ap = argparse.ArgumentParser()
    ap.add_argument("--samples", default=str(ROOT / "data/alpha/score_backtest/samples.csv.gz"))
    ap.add_argument("--ohlcv", required=True)
    ap.add_argument("--cost-pct", type=float, default=0.15, help="one-way, percent per unit weight change")
    args = ap.parse_args()
    cost = args.cost_pct / 100

    px = pd.read_pickle(args.ohlcv)
    close, high, low = px["Close"], px["High"], px["Low"]
    try:
        import yfinance as yf

        irx = yf.download("^IRX", start=str(close.index[0].date()), progress=False, auto_adjust=False)["Close"]
        irx = irx.squeeze()
        irx.index = pd.DatetimeIndex(irx.index).tz_localize(None).normalize()
        rf_all = (irx.reindex(close.index).ffill().bfill() / 100 / 252).fillna(0.0)
    except Exception:
        rf_all = pd.Series(0.0, index=close.index)
    spy_on = regime_series(close["SPY"].dropna(), 200, 1.0).reindex(close.index).ffill().fillna(1.0)

    s = pd.read_csv(args.samples, usecols=["ticker", "as_of_date"])
    spans = s.groupby("ticker").as_of_date.agg(["min", "max"])
    per, port, years = [], {}, {}
    for t, (d0, d1) in spans.iterrows():
        if t not in close:
            continue
        c_full = close[t].dropna()
        if len(c_full) < 400:
            continue
        tr = pd.concat([high[t] - low[t], (high[t] - c_full.shift()).abs(), (low[t] - c_full.shift()).abs()], axis=1).max(axis=1)
        atr = tr.reindex(c_full.index).ewm(alpha=1 / 14, adjust=False).mean()
        t200 = trend_sma(c_full, 200)
        vt = vol_target(c_full)
        spy = spy_on.reindex(c_full.index).ffill().fillna(1.0)
        rules = {
            "buy_hold": pd.Series(1.0, index=c_full.index),
            "trend_200d": t200,
            "trend_200d_half": 0.5 + 0.5 * t200,
            "golden_cross": golden_cross(c_full),
            "momentum_12m": momentum(c_full),
            "stop_3atr": chandelier(c_full, atr, 3.0),
            "stop_20pct": pct_stop(c_full, 0.20),
            "vol_target": vt,
            "vol_target_trend_half": vt * (0.5 + 0.5 * t200),
            "spy_regime_half": 0.5 + 0.5 * spy,
        }
        sl = slice(pd.Timestamp(d0), pd.Timestamp(d1))
        ret = c_full.pct_change().fillna(0.0).loc[sl]
        if len(ret) < 252:
            continue
        rf = rf_all.reindex(ret.index).fillna(0.0)
        row = {"ticker": t}
        for k, w in rules.items():
            w = w.shift(1).loc[sl].fillna(1.0)
            strat = w * ret + (1 - w) * rf - w.diff().abs().fillna(0.0) * cost
            port.setdefault(k, []).append(strat.rename(t))
            for m, v in _metrics(strat, rf).items():
                row[f"{k}_{m}"] = v
            row[f"{k}_avg_weight"] = 100 * float(w.mean())
            row[f"{k}_turnover"] = float(w.diff().abs().sum() / (len(w) / 252))
        per.append(row)
    per = pd.DataFrame(per)
    rf_p = rf_all
    rep: dict = {"n_stocks": int(len(per)), "cost_one_way_pct": args.cost_pct, "rules": {}}
    for k in port:
        ew = pd.concat(port[k], axis=1).mean(axis=1)
        d = {
            "median_stock": {m: round(float(per[f"{k}_{m}"].median()), 3)
                             for m in ("cagr", "sharpe", "max_dd", "avg_weight", "turnover")},
            "equal_weight_portfolio": {m: round(float(v), 3) for m, v in _metrics(ew, rf_p.reindex(ew.index).fillna(0.0)).items()},
            "by_year_ew_return_pct": {str(y): round(100 * float((1 + g).prod() - 1), 2) for y, g in ew.groupby(ew.index.year)},
        }
        if k != "buy_hold":
            d["pct_stocks_beating_buy_hold"] = {
                "cagr": round(100 * float((per[f"{k}_cagr"] > per["buy_hold_cagr"]).mean()), 1),
                "sharpe": round(100 * float((per[f"{k}_sharpe"] > per["buy_hold_sharpe"]).mean()), 1),
                "smaller_drawdown": round(100 * float((per[f"{k}_max_dd"] > per["buy_hold_max_dd"]).mean()), 1),
            }
        rep["rules"][k] = d
    rep["examples"] = per[per.ticker.isin(EXAMPLES)].set_index("ticker").round(2).to_dict(orient="index")
    out = Path(args.samples).with_name("timing_rules_backtest.json")
    out.write_text(json.dumps(rep, indent=2, default=float))
    per.to_csv(Path(args.samples).with_name("timing_rules_per_stock.csv"), index=False)
    for k, d in rep["rules"].items():
        print(k, d["median_stock"], d["equal_weight_portfolio"], d.get("pct_stocks_beating_buy_hold"))


if __name__ == "__main__":
    main()
