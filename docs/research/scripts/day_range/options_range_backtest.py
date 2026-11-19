"""Backtest: options-implied 80% close range (ATM weekly straddle) vs our EWMA range, 2 years, 10 big names.
Fetch: Polygon free tier (2y end-of-day option aggregates, 5 calls/min), cached per contract in dr_bt/polygon_opts/.
  python options_range_backtest.py fetch     (resumable; ~7 h)
  python options_range_backtest.py analyze
Forecast for day t uses closes at t-1 only: straddle(t-1) of the week's Friday expiry, strike set from the prior Friday close."""
import json, math, os, sys, time, urllib.request
from datetime import date, timedelta
from pathlib import Path
import numpy as np, pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "backend"))
TICKERS = ["SPY", "QQQ", "AAPL", "MSFT", "NVDA", "AMZN", "TSLA", "META", "GOOGL", "AMD"]
CACHE = Path("/home/ubuntu/dr_bt/polygon_opts"); CACHE.mkdir(parents=True, exist_ok=True)
START = date(2024, 11, 22)
PACE = 12.5


def closes():
    p = Path("/home/ubuntu/dr_bt/opt_bt_closes.pkl")
    if p.exists():
        return pd.read_pickle(p)
    import yfinance as yf
    c = yf.download(TICKERS, start="2023-06-01", auto_adjust=False, progress=False)["Close"]
    c.index = pd.to_datetime(c.index).date
    c.to_pickle(p)
    return c


def occ(u, exp, cp, k):
    return f"O:{u}{exp:%y%m%d}{cp}{int(round(k * 1000)):08d}"


def get_aggs(sym, a, b):
    f = CACHE / f"{sym.replace(':', '_')}_{a}_{b}.json"
    if f.exists():
        return json.loads(f.read_text())
    key = os.environ["POLYGON_API_KEY"].strip()
    u = f"https://api.polygon.io/v2/aggs/ticker/{sym}/range/1/day/{a}/{b}?adjusted=false&limit=50"
    for _ in range(3):
        try:
            r = json.loads(urllib.request.urlopen(urllib.request.Request(u, headers={"Authorization": f"Bearer {key}"}), timeout=30).read())
            break
        except urllib.error.HTTPError as e:
            r = {"http": e.code}
            if e.code != 429:
                break
            time.sleep(60)
        except Exception:
            r = {"err": 1}; time.sleep(20)
    time.sleep(PACE)
    out = {str(pd.Timestamp(x["t"], unit="ms", tz="America/New_York").date()): x["c"] for x in r.get("results") or []}
    if "err" not in r and r.get("http") != 429:
        f.write_text(json.dumps(out))
    return out


def weeks():
    e = START
    while e <= date.today() - timedelta(days=1):
        yield e
        e += timedelta(days=7)


def fetch():
    c = closes()
    for exp in weeks():
        prev_fri = exp - timedelta(days=7)
        for u in TICKERS:
            s = c[u].get(prev_fri)
            if s is None or not np.isfinite(s):
                continue
            for inc in (5.0, 2.5, 1.0):
                k = round(s / inc) * inc
                ca = get_aggs(occ(u, exp, "C", k), prev_fri, exp)
                if ca:
                    get_aggs(occ(u, exp, "P", k), prev_fri, exp)
                    break
        print(exp, flush=True)


def _bachelier_sd(ext_frac: float, m: float) -> float | None:
    """Total sd (fraction of spot) implied by straddle time value at moneyness m=|S-K|/S (normal model).
    Time value alone understates the ATM straddle once spot drifts from the fixed strike, so invert instead."""
    from scipy.stats import norm

    def tv(sd):
        d = m / sd
        return 2 * sd * (norm.pdf(d) - d * norm.sf(d))
    lo, hi = 1e-5, 0.5
    if ext_frac <= tv(lo) or ext_frac >= tv(hi):
        return None
    for _ in range(60):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if tv(mid) < ext_frac else (lo, mid)
    sd = (lo + hi) / 2
    return sd if m / sd <= 2.0 else None


def analyze():
    from signals.stock_day_range import ewma_sigmas, Z80, CLOSE_K
    from signals.statistical_validation import newey_west_t_stat, deflated_sharpe_ratio
    c = closes()
    rows = []
    for u in TICKERS:
        s = c[u].dropna()
        sig = dict(zip(s.index, ewma_sigmas(list(s.values))))
        days = list(s.index)
        for exp in weeks():
            prev_fri = exp - timedelta(days=7)
            s0 = s.get(prev_fri)
            if s0 is None:
                continue
            for inc in (5.0, 2.5, 1.0):
                k = round(s0 / inc) * inc
                ca = get_aggs(occ(u, exp, "C", k), prev_fri, exp) if (CACHE / f"{occ(u, exp, 'C', k).replace(':', '_')}_{prev_fri}_{exp}.json").exists() else None
                if ca:
                    pa = json.loads((CACHE / f"{occ(u, exp, 'P', k).replace(':', '_')}_{prev_fri}_{exp}.json").read_text()) \
                        if (CACHE / f"{occ(u, exp, 'P', k).replace(':', '_')}_{prev_fri}_{exp}.json").exists() else {}
                    break
            else:
                continue
            wk = [d for d in days if prev_fri < d <= exp]
            for t in wk:
                i = days.index(t); tp = days[i - 1]
                cv, pv, sp = ca.get(str(tp)), pa.get(str(tp)), s[tp]
                if not cv or not pv or not sig.get(tp):
                    continue
                ext = cv + pv - abs(sp - k)
                n_left = sum(1 for d in wk if d >= t)
                if ext <= 0 or n_left < 1:
                    continue
                sd_tot = _bachelier_sd(ext / sp, abs(sp - k) / sp)
                if sd_tot is None:
                    continue
                sd_opt = sd_tot / math.sqrt(n_left)
                rows.append(dict(t=t, u=u, r=math.log(s[t] / sp), ours=CLOSE_K * sig[tp], opt=sd_opt))
    df = pd.DataFrame(rows)
    df["blend"] = (df.ours + df.opt) / 2
    a = df.r.abs()
    for m in ("ours", "opt", "blend"):
        hw = Z80 * df[m]
        df[f"in_{m}"] = a <= hw
        df[f"is_{m}"] = 2 * hw + 10 * (a - hw).clip(lower=0)
    wk = pd.to_datetime(df.t).dt.to_period("W-FRI")
    df["bad_wk"] = wk.map(df.groupby(wk).in_ours.mean() < 0.70)
    print("rows", len(df), "days", df.t.nunique(), "tickers", df.u.nunique(), df.t.min(), df.t.max())
    for lab, x in (("all", df), ("weeks ours<70%", df[df.bad_wk]), ("other weeks", df[~df.bad_wk])):
        print(f"{lab:16s} n={len(x):5d} | cover80 ours {x.in_ours.mean()*100:5.1f} opt {x.in_opt.mean()*100:5.1f} blend {x.in_blend.mean()*100:5.1f}"
              f" | width ours {x.ours.mean()*Z80*100:.2f}% opt {x.opt.mean()*Z80*100:.2f}% | IS ours {x.is_ours.mean()*100:.3f} opt {x.is_opt.mean()*100:.3f} blend {x.is_blend.mean()*100:.3f}")
    print("by ticker cover80 ours/opt:", {u: (round(g.in_ours.mean()*100), round(g.in_opt.mean()*100)) for u, g in df.groupby("u")})
    daily = df.groupby("t")[["is_ours", "is_opt", "is_blend"]].mean()
    for m in ("opt", "blend"):
        g = daily.is_ours - daily[f"is_{m}"]
        print(m, "IS gain %.1f%%" % (g.mean() / daily.is_ours.mean() * 100), "HAC t", round(newey_west_t_stat(g.values, lags=5), 2),
              "DSR", deflated_sharpe_ratio(g.values, n_trials=2)["dsr"])
    # Calibrated variant: one scale factor for the options sd fit on the first half (5-day embargo), tested on the second.
    days_sorted = sorted(df.t.unique()); mid_t = days_sorted[len(days_sorted) // 2]
    tr = df[df.t < days_sorted[len(days_sorted) // 2 - 5]]; te = df[df.t >= mid_t].copy()
    scale = float((tr.r.abs() / (Z80 * tr.opt)).quantile(0.80))
    te["optc"] = te.opt * scale; te["blendc"] = (te.ours + te.optc) / 2
    ta = te.r.abs()
    for m in ("ours", "optc", "blendc"):
        hw = Z80 * te[m]; te[f"in_{m}"] = ta <= hw; te[f"is_{m}"] = 2 * hw + 10 * (ta - hw).clip(lower=0)
    print(f"CLOSE_K {CLOSE_K} | calibrated opt scale (train) {scale:.2f} | test n={len(te)} from {mid_t}")
    for lab, x in (("test all", te), ("test bad wks", te[te.bad_wk]), ("test other", te[~te.bad_wk])):
        print(f"  {lab:13s} cover80 ours {x.in_ours.mean()*100:5.1f} optc {x.in_optc.mean()*100:5.1f} blendc {x.in_blendc.mean()*100:5.1f}"
              f" | IS ours {x.is_ours.mean()*100:.3f} optc {x.is_optc.mean()*100:.3f} blendc {x.is_blendc.mean()*100:.3f}")
    dte = te.groupby("t")[["is_ours", "is_optc", "is_blendc"]].mean()
    for m in ("optc", "blendc"):
        g = dte.is_ours - dte[f"is_{m}"]
        print(" ", m, "test IS gain %.1f%%" % (g.mean() / dte.is_ours.mean() * 100), "HAC t", round(newey_west_t_stat(g.values, lags=5), 2),
              "DSR", deflated_sharpe_ratio(g.values, n_trials=4)["dsr"])
    print("first/second half IS gain (opt, blend):")
    mid = sorted(daily.index)[len(daily) // 2]
    for lab, x in (("H1", daily[daily.index < mid]), ("H2", daily[daily.index >= mid])):
        print(" ", lab, [round((x.is_ours - x[f"is_{m}"]).mean() / x.is_ours.mean() * 100, 1) for m in ("opt", "blend")])


if __name__ == "__main__":
    {"fetch": fetch, "analyze": analyze}[sys.argv[1]]()
