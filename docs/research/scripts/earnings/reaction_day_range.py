"""Day-range card on earnings reaction days: how well do the normal close bands cover the reaction close?
A) evening before (centre = pre-report close): normal 80% band (0.97σ20) vs the earnings 80% band.
B) after the report (centre = reaction-day open, proxy for pre-market): normal 0.80σ20 band vs scaled bands.
Fit multipliers on reports before 2021, test 2021+. Needs d10.pkl, er.pkl (see README)."""
import math
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "backend")
from signals.earnings_move import forecast, reaction_index  # noqa: E402
from signals.stock_day_range import CLOSE_K, PRE_K, Z80, ewma_sigmas  # noqa: E402

D = sys.argv[1] if len(sys.argv) > 1 else "/home/ubuntu/dr_bt"
d10, er = pd.read_pickle(f"{D}/d10.pkl"), pd.read_pickle(f"{D}/er.pkl")
rows = []
for t, ed in er.items():
    if t not in d10.columns.get_level_values(0):
        continue
    px = d10[t][["Open", "Close"]].dropna()
    if len(px) < 300 or ed is None or ed.empty:
        continue
    idx = pd.DatetimeIndex(px.index).tz_localize(None).normalize()
    c, o = px["Close"].values.astype(float), px["Open"].values.astype(float)
    sig = ewma_sigmas(list(c))
    cs = pd.Series(c, index=idx)
    ed = ed[~ed.index.duplicated()]
    for ts, rep in zip(ed.index, ed["Reported EPS"]):
        if pd.isna(rep):
            continue
        ri = reaction_index(idx, ts)
        if not ri:
            continue
        pre, react = ri
        s = sig[pre]
        if not s or pre < 260:
            continue
        f = forecast(cs.iloc[: pre + 1], ed[ed.index < ts], float(c[pre]))
        if not f:
            continue
        rows.append({"t": t, "year": idx[react].year, "sig": s, "move80": f["move80_pct"] / 100,
                     "typ": f["typical_move_pct"] / 100,
                     "full": abs(math.log(c[react] / c[pre])), "post": abs(math.log(c[react] / o[react]))})
df = pd.DataFrame(rows)
tr, te = df[df.year < 2021], df[df.year >= 2021]
print(f"reports: {len(df)} (train {len(tr)}, test {len(te)}), tickers {df.t.nunique()}")


def cov(x, w):
    return round(100 * float(np.mean(x <= w)), 1)


print("\nA) evening before, close-to-close")
for name, g in (("train", tr), ("test", te)):
    print(f"  {name}: normal band {cov(g.full, Z80 * CLOSE_K * g.sig)}% | earnings band {cov(g.full, np.log(1 + g.move80))}%")

print("\nB) after the report, open-to-close")
m_sig = float(np.quantile(tr.post / (Z80 * PRE_K * tr.sig), 0.8))
m_typ = float(np.quantile(tr.post / (Z80 * tr.typ), 0.8))
print(f"  fit on train: sigma multiplier {m_sig:.2f}; per-typical-move k {m_typ:.2f}")
for name, g in (("train", tr), ("test", te)):
    base = Z80 * PRE_K * g.sig
    print(f"  {name}: normal {cov(g.post, base)}% | x{m_sig:.2f} sigma {cov(g.post, m_sig * base)}% | "
          f"max(normal, {m_typ:.2f}*typ) {cov(g.post, np.maximum(base, Z80 * m_typ * g.typ))}%")
for y, g in te.groupby("year"):
    print(f"   {y}: n={len(g)} normal {cov(g.post, Z80 * PRE_K * g.sig)}% scaled {cov(g.post, m_sig * Z80 * PRE_K * g.sig)}%")
lo, hi = te.sig.quantile([1 / 3, 2 / 3])
for lab, g in (("calm", te[te.sig <= lo]), ("mid", te[(te.sig > lo) & (te.sig <= hi)]), ("jumpy", te[te.sig > hi])):
    print(f"   {lab}: n={len(g)} scaled {cov(g.post, m_sig * Z80 * PRE_K * g.sig)}%")
