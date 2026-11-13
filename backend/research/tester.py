"""Event-driven rule backtest on the point-in-time panel.

Signal at day t's close -> enter at t+1 open -> exit at the first of stop, target or
``hold_days`` closes. Stop and target are checked on daily lows/highs from the entry day;
a gap through a level fills at the open; if one day touches both, the stop is assumed.
One position per ticker at a time. Costs are a round trip in bps, split across entry and exit.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from research.dsl import describe, evaluate, family_key
from research.features import BENCH, FeatureCache

MAX_TRADES = 60000
CURVE_POINTS = 400


def _r(x, n=2):
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) or math.isinf(f) else round(f, n)


def simulate(O, H, L, C, sig, hold: int, stop_pct: float | None, target_pct: float | None, start_i: int, end_i: int):
    """Returns list of (j, sig_i, entry_i, exit_i, entry_px, exit_px, reason)."""
    T, N = C.shape
    trades = []
    for j in range(N):
        cand = np.flatnonzero(sig[start_i:end_i + 1, j]) + start_i
        free = 0
        for i in cand:
            if i < free:
                continue
            e = i + 1
            if e > end_i:
                break
            px = O[e, j]
            if not np.isfinite(px) or px <= 0:
                continue
            last = min(e + hold - 1, end_i)
            sp = px * (1 - stop_pct / 100) if stop_pct else None
            tp = px * (1 + target_pct / 100) if target_pct else None
            exit_i, exit_px, reason = None, None, None
            for k in range(e, last + 1):
                o, h, l, c = O[k, j], H[k, j], L[k, j], C[k, j]
                if not np.isfinite(c):
                    exit_i = k - 1 if k > e else e
                    exit_px = C[exit_i, j] if np.isfinite(C[exit_i, j]) else px
                    reason = "data_end"
                    break
                if k > e and sp is not None and np.isfinite(o) and o <= sp:
                    exit_i, exit_px, reason = k, o, "stop_gap"
                    break
                if k > e and tp is not None and np.isfinite(o) and o >= tp:
                    exit_i, exit_px, reason = k, o, "target"
                    break
                if sp is not None and np.isfinite(l) and l <= sp:
                    exit_i, exit_px, reason = k, sp, "stop"
                    break
                if tp is not None and np.isfinite(h) and h >= tp:
                    exit_i, exit_px, reason = k, tp, "target"
                    break
            if exit_i is None:
                exit_i, exit_px = last, C[last, j]
                reason = "time" if last == e + hold - 1 else "open"
            trades.append((j, int(i), e, int(exit_i), float(px), float(exit_px), reason))
            free = exit_i + 1
            if len(trades) > MAX_TRADES:
                raise ValueError(f"rule fires too often (> {MAX_TRADES} trades); add a condition or use 'on change' entries")
    return trades


def _stats(net: np.ndarray) -> dict[str, Any]:
    if not len(net):
        return {"n": 0}
    w, l = net[net > 0], net[net <= 0]
    return {
        "n": int(len(net)),
        "win_rate": _r(len(w) / len(net) * 100, 1),
        "mean": _r(net.mean()),
        "median": _r(np.median(net)),
        "avg_win": _r(w.mean()) if len(w) else None,
        "avg_loss": _r(l.mean()) if len(l) else None,
        "payoff": _r(w.mean() / abs(l.mean())) if len(w) and len(l) and l.mean() != 0 else None,
        "worst": _r(net.min()),
        "best": _r(net.max()),
        "p10": _r(np.percentile(net, 10)),
    }


def _curve(trades, O, C, dates, cost_frac, start_i, end_i):
    T = len(dates)
    s, n = np.zeros(T), np.zeros(T)
    for (j, _, e, x, px, xp, _r_) in trades:
        if x == e:
            rets = [xp / px - 1]
        else:
            path = C[e:x, j]
            rets = [path[0] / px - 1] + list(path[1:] / path[:-1] - 1) + [xp / path[-1] - 1]
        rets = np.nan_to_num(np.asarray(rets, dtype=float))
        rets[0] -= cost_frac / 2
        rets[-1] -= cost_frac / 2
        s[e:x + 1] += rets
        n[e:x + 1] += 1
    day = np.where(n > 0, s / np.maximum(n, 1), 0.0)[start_i:end_i + 1]
    return day, n[start_i:end_i + 1]


def _dd(eq: np.ndarray) -> float:
    return float((eq / np.maximum.accumulate(eq) - 1).min() * 100) if len(eq) else 0.0


def _cagr(eq: np.ndarray, years: float) -> float | None:
    return (eq[-1] ** (1 / years) - 1) * 100 if years > 0.25 and eq[-1] > 0 else None


def backtest(fc: FeatureCache, rule: dict, *, hold_days: int = 20, stop_pct: float | None = None,
             target_pct: float | None = None, cost_bps: float = 10.0, entry: str = "on_change",
             split_date: str = "2019-01-01", start: str | None = None, end: str | None = None,
             include_etfs: bool = False, n_trials: int = 1, variant_months: list[dict] | None = None) -> dict[str, Any]:
    from signals.statistical_validation import probability_of_backtest_overfitting, promotion_check

    p = fc.p
    if not 1 <= int(hold_days) <= 252:
        raise ValueError("hold_days must be 1-252")
    for v, nm in ((stop_pct, "stop_pct"), (target_pct, "target_pct")):
        if v is not None and not 0 < float(v) < 100:
            raise ValueError(f"{nm} must be between 0 and 100")
    hold = int(hold_days)
    dates = p.close.index
    warm = 252
    start_i = max(warm, int(dates.searchsorted(pd.Timestamp(start)))) if start else warm
    end_i = int(dates.searchsorted(pd.Timestamp(end), side="right")) - 1 if end else len(dates) - 1
    if end_i - start_i < 60:
        raise ValueError("test window too short")

    sig = evaluate(rule, fc) & p.members
    if not include_etfs:
        sig.loc[:, [t for t in p.etfs if t in sig.columns]] = False
    if entry == "on_change":
        sig = sig & ~sig.shift(1, fill_value=False)
    elif entry != "every":
        raise ValueError("entry must be 'on_change' or 'every'")
    cols = list(p.close.columns)
    O, H, L, C = (getattr(p, f).to_numpy(dtype=float) for f in ("open", "high", "low", "close"))
    trades = simulate(O, H, L, C, sig.to_numpy(), hold, stop_pct, target_pct, start_i, end_i)

    cost = cost_bps / 1e4
    jb = cols.index(BENCH) if BENCH in cols else None
    member_np = p.members.to_numpy()
    fwd_all = np.full(len(dates), np.nan)
    if hold < len(dates):
        fwd = C[hold:, :] / O[1:len(dates) - hold + 1, :] - 1
        fwd = np.where(member_np[: len(dates) - hold], fwd, np.nan)
        if not include_etfs:
            for t in p.etfs:
                if t in cols:
                    fwd[:, cols.index(t)] = np.nan
        import warnings

        with warnings.catch_warnings(), np.errstate(all="ignore"):
            warnings.simplefilter("ignore", RuntimeWarning)
            fwd_all[: len(dates) - hold] = np.nanmean(np.where(np.isfinite(fwd), fwd, np.nan), axis=1)

    rows = []
    for (j, si, e, x, px, xp, reason) in trades:
        gross = (xp / px - 1) * 100
        spy = (C[x, jb] / O[e, jb] - 1) * 100 if jb is not None and np.isfinite(O[e, jb]) else np.nan
        rows.append({
            "ticker": cols[j], "sector": p.sectors.get(cols[j]), "signal_date": dates[si], "entry_date": dates[e],
            "exit_date": dates[x], "entry": px, "exit": xp, "bars": x - e + 1, "reason": reason,
            "gross": gross, "net": gross - cost_bps / 100, "spy": spy, "base": fwd_all[si] * 100,
        })
    df = pd.DataFrame(rows)
    split = pd.Timestamp(split_date) if split_date else None
    closed = df[df["reason"] != "open"] if len(df) else df

    def part(d: pd.DataFrame) -> dict[str, Any]:
        st = _stats(d["net"].to_numpy()) if len(d) else {"n": 0}
        if len(d):
            st["vs_spy"] = _r((d["net"] - d["spy"]).mean())
            st["vs_random"] = _r((d["net"] - d["base"]).mean())
            st["spy_mean"] = _r(d["spy"].mean())
        return st

    out: dict[str, Any] = {
        "rule": rule, "rule_text": describe(rule), "family": family_key(rule),
        "params": {"hold_days": hold, "stop_pct": stop_pct, "target_pct": target_pct, "cost_bps": cost_bps,
                   "entry": entry, "split_date": split_date, "start": str(dates[start_i].date()),
                   "end": str(dates[end_i].date()), "include_etfs": include_etfs},
        "panel": {"as_of": p.meta.get("as_of"), "n_tickers": p.meta.get("n_tickers"), "missing_n": len(p.meta.get("missing") or [])},
    }
    out["all"] = part(closed)
    if split is not None and len(closed):
        out["in_sample"] = part(closed[closed["entry_date"] < split])
        out["out_of_sample"] = part(closed[closed["entry_date"] >= split])
    out["open_trades"] = int((df["reason"] == "open").sum()) if len(df) else 0
    out["exit_reasons"] = df["reason"].value_counts().to_dict() if len(df) else {}

    if len(closed):
        closed = closed.assign(year=closed["entry_date"].dt.year)
        out["by_year"] = [{"year": int(y), **part(g)} for y, g in closed.groupby("year")]
        out["by_sector"] = sorted(({"sector": s or "Unknown", **part(g)} for s, g in closed.groupby(closed["sector"].fillna("Unknown"))),
                                  key=lambda r: -r["n"])
        hist, edges = np.histogram(np.clip(closed["net"], -50, 50), bins=40, range=(-50, 50))
        out["histogram"] = {"edges": [float(e) for e in edges], "counts": hist.tolist()}

    day, nopen = _curve(trades, O, C, dates, cost, start_i, end_i)
    d_idx = dates[start_i:end_i + 1]
    eq = np.cumprod(1 + day)
    if jb is not None:
        sc = pd.Series(C[start_i:end_i + 1, jb]).ffill().bfill().to_numpy()
        spy_eq = sc / sc[0]
    else:
        spy_eq = np.ones(len(d_idx))
    years = (d_idx[-1] - d_idx[0]).days / 365.25
    step = max(1, len(d_idx) // CURVE_POINTS)
    out["curve"] = {
        "dates": [str(d.date()) for d in d_idx[::step]],
        "strategy": [_r(v, 4) for v in eq[::step]],
        "spy": [_r(v, 4) for v in spy_eq[::step]],
        "open": [int(v) for v in nopen[::step]],
    }
    sd = day.std(ddof=1) if len(day) > 2 else 0
    out["portfolio"] = {
        "cagr": _r(_cagr(eq, years)), "spy_cagr": _r(_cagr(spy_eq, years)),
        "max_dd": _r(_dd(eq)), "spy_max_dd": _r(_dd(spy_eq)),
        "sharpe": _r(day.mean() / sd * np.sqrt(252)) if sd > 0 else None,
        "exposure_pct": _r((nopen > 0).mean() * 100, 1), "avg_open": _r(nopen[nopen > 0].mean() if (nopen > 0).any() else 0, 1),
        "note": "Equal weight across open trades, rebalanced daily; cash earns 0 when nothing is open.",
    }
    monthly = pd.Series(day, index=d_idx).resample("ME").apply(lambda r: float(np.prod(1 + r) - 1))
    out["monthly"] = {str(k.date())[:7]: round(float(v), 6) for k, v in monthly.items()}

    oos = closed[closed["entry_date"] >= split] if split is not None and len(closed) else closed
    vm = None
    if variant_months:
        mats = [pd.Series(out["monthly"])] + [pd.Series(v) for v in variant_months]
        m = pd.concat(mats, axis=1).dropna()
        if split is not None:
            m = m[m.index >= str(split.date())[:7]]
        if m.shape[1] >= 2 and len(m) >= 32:
            vm = m.to_numpy()
    if len(oos):
        pc = promotion_check(oos["gross"].tolist(), n_trials=max(1, n_trials), holding_bars=hold, cost_bps=cost_bps,
                             variant_matrix=vm, baseline_returns_pct=(oos["base"] + cost_bps / 100).dropna().tolist())
    else:
        pc = {"n": 0, "passes": False, "fails": ["no out-of-sample trades"], "n_trials": n_trials}
    pc["sample"] = "out_of_sample" if split is not None else "all"
    pc["baseline"] = "random member stock entered the same day, same hold"
    out["promotion"] = pc

    tr = df.sort_values("entry_date", ascending=False) if len(df) else df
    out["trades"] = [{
        "ticker": r.ticker, "sector": r.sector, "signal_date": str(r.signal_date.date()), "entry_date": str(r.entry_date.date()),
        "exit_date": str(r.exit_date.date()), "entry": _r(r.entry), "exit": _r(r.exit), "bars": int(r.bars),
        "reason": r.reason, "net_pct": _r(r.net), "spy_pct": _r(r.spy),
    } for r in tr.head(5000).itertuples()]
    out["trades_total"] = int(len(df))
    return out
