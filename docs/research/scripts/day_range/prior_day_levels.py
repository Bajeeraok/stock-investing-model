"""Do yesterday's high / low / close act as intraday support or resistance?
First touch of each level per day (5-min RTH bars): 'bounce' = price moves X back away from the level before
moving X through it (X = 0.25 × daily σ20). Compared with placebo levels shifted ±0.35σ from the real ones.
Needs m5.pkl (60d 5-min, prepost) and d10.pkl (daily)."""
import math
import sys

import numpy as np
import pandas as pd

D = sys.argv[1] if len(sys.argv) > 1 else "/home/ubuntu/dr_bt"
m5, d10 = pd.read_pickle(f"{D}/m5.pkl"), pd.read_pickle(f"{D}/d10.pkl")
X_K, SHIFT = 0.25, 0.35
tickers = sorted(set(m5.columns.get_level_values(0)))
mi = m5.index.tz_convert("America/New_York")
rth = (mi.hour * 60 + mi.minute >= 570) & (mi.hour * 60 + mi.minute < 960)
m5 = m5[rth]
days_all = pd.Index(sorted(set(mi[rth].date)))


def test_level(h, l, L, sig_x, above):
    """above: level above the open → resistance test. Returns 'bounce'/'break'/None (untouched/unresolved)."""
    n = len(h)
    for i in range(1, n):
        touched = (h[i] >= L and h[i - 1] < L) if above else (l[i] <= L and l[i - 1] > L)
        if not touched:
            continue
        away, through = (L * math.exp(-sig_x), L * math.exp(sig_x)) if above else (L * math.exp(sig_x), L * math.exp(-sig_x))
        for j in range(i, n):
            if j > i or True:
                hit_away = l[j] <= away if above else h[j] >= away
                hit_thru = h[j] >= through if above else l[j] <= through
                if hit_thru and hit_away:
                    return None  # same bar, ambiguous
                if hit_thru:
                    return "break"
                if hit_away:
                    return "bounce"
        return None
    return None


rows = []
for t in tickers:
    if t not in d10.columns.get_level_values(0):
        continue
    df = m5[t][["Open", "High", "Low", "Close"]].dropna()
    if df.empty:
        continue
    dts = df.index.tz_convert("America/New_York").date
    dc = d10[t]["Close"].dropna()
    dsig = np.log(dc).diff().ewm(span=20).std()
    dsig.index = pd.DatetimeIndex(dsig.index).tz_localize(None).normalize()
    groups = {d: g for d, g in df.groupby(dts)}
    ds = sorted(groups)
    for k in range(1, len(ds)):
        y, g = groups[ds[k - 1]], groups[ds[k]]
        if len(g) < 40 or len(y) < 40:
            continue
        s = dsig[dsig.index < pd.Timestamp(ds[k])]
        if s.empty or not s.iloc[-1] > 0:
            continue
        sig = float(s.iloc[-1])
        h, l, o = g["High"].values, g["Low"].values, float(g["Open"].iloc[0])
        real = {"prev_high": float(y["High"].max()), "prev_low": float(y["Low"].min()), "prev_close": float(y["Close"].iloc[-1])}
        for name, L in real.items():
            for kind, lev in (("real", L), ("placebo", L * math.exp(SHIFT * sig)), ("placebo", L * math.exp(-SHIFT * sig))):
                if abs(math.log(lev / o)) < 0.05 * sig:
                    continue  # opened on it
                above = lev > o
                r = test_level(h, l, lev, X_K * sig, above)
                if r:
                    rows.append({"t": t, "day": ds[k], "level": name, "kind": kind, "side": "resistance" if above else "support",
                                 "bounce": r == "bounce"})
r = pd.DataFrame(rows)
cut = sorted(r.day.unique())[len(r.day.unique()) // 2]
print(f"touches resolved: {len(r)}, tickers {r.t.nunique()}, days {r.day.nunique()}")
for half, g in (("first half", r[r.day < cut]), ("second half", r[r.day >= cut]), ("all", r)):
    print(f"\n{half}")
    tab = g.groupby(["level", "side", "kind"]).bounce.agg(["mean", "count"]).unstack("kind")
    print((tab.round(3)).to_string())
