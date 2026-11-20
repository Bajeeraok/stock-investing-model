"""Fixes for the day range in falling markets: storm widening, faster volatility, shock memory, downside skew.
Baseline: close inside prev close × exp(±Z80·CLOSE_K·σ_EWMA20(t-1)). Variants change lower/upper half-widths
using only data known at the prior close. Score: two-sided interval score (lower = better).
Train 2016–2020 picks the best variant; ~20-session embargo; test 2021-02+. Data: dr_bt/d10.pkl, dr_bt/vix.pkl."""
import os, sys, itertools
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "backend"))
from signals.stock_day_range import ewma_sigmas, Z80, CLOSE_K
from signals.statistical_validation import newey_west_t_stat, deflated_sharpe_ratio, probability_of_backtest_overfitting

D = Path("/home/ubuntu/dr_bt")
d = pd.read_pickle(D / os.environ.get("DATA", "d10.pkl"))
c = d.xs("Close", axis=1, level="Price").sort_index()
v = pd.read_pickle(D / os.environ.get("VIX", "vix.pkl")).reindex(c.index).ffill()
sig = pd.DataFrame({t: ewma_sigmas(list(c[t].ffill().values)) for t in c.columns}, index=c.index).astype(float)
sig5 = pd.DataFrame({t: ewma_sigmas(list(c[t].ffill().values), span=5) for t in c.columns}, index=c.index).astype(float)
sig[c.isna()] = np.nan; sig5[c.isna()] = np.nan
r = np.log(c / c.shift(1))
s20, s5 = sig.shift(1) * CLOSE_K, sig5.shift(1) * CLOSE_K
spy = c["SPY"]
below50 = (spy < spy.rolling(50).mean())
storm = below50.rolling(5).sum().ge(3).shift(1).fillna(False)          # mostly below 50-day, known at prior close
dd = (spy / spy.rolling(60).max() - 1).shift(1)
deep = (dd < -0.07) & storm
vixhi = (v["^VIX"] > 25).shift(1).fillna(False)
shock = (r.abs() / sig.shift(1)).shift(1)                               # yesterday's move in σ units
ok = r.notna() & s20.notna() & s5.notna()
TRAIN, TEST = ("2016-01-01", "2020-12-31"), "2021-02-01"

def score(lo, hi):
    """lo/hi: half-widths in log units below/above the prior close."""
    L, U = -Z80 * lo, Z80 * hi
    inside = ((r >= L) & (r <= U)).where(ok)
    isc = ((U - L) + 10 * (L - r).clip(lower=0) + 10 * (r - U).clip(lower=0)).where(ok)
    return inside, isc

def cond(mask, k):
    return pd.DataFrame(np.repeat(np.where(mask.values.astype(bool)[:, None], k, 1.0), c.shape[1], axis=1), index=c.index, columns=c.columns)

V = {}
for k in (1.1, 1.2, 1.3, 1.5):
    V[("storm_both", k)] = score(s20 * cond(storm, k), s20 * cond(storm, k))
    V[("storm_down", k)] = score(s20 * cond(storm, k), s20)
    V[("deep_both", k)] = score(s20 * cond(deep, k), s20 * cond(deep, k))
    V[("vix25_both", k)] = score(s20 * cond(vixhi, k), s20 * cond(vixhi, k))
for w in (0.25, 0.5, 0.75):
    s = (1 - w) * s20 + w * s5
    V[("fast_mix", w)] = score(s, s)
V[("fast_max", 1)] = score(np.maximum(s20, s5), np.maximum(s20, s5))
for a in (0.1, 0.2, 0.3):
    m = (1 + a * (shock - 1).clip(lower=0)).clip(upper=2.0).fillna(1.0)
    V[("shock", a)] = score(s20 * m, s20 * m)

base_in, base_is = score(s20, s20)
day_base = base_is.mean(axis=1)
imp = pd.DataFrame({k: day_base - isc.mean(axis=1) for k, (_, isc) in V.items()})
tr, te = imp.loc[TRAIN[0]:TRAIN[1]].dropna(), imp.loc[TEST:].dropna()
best = tr.mean().idxmax()
print("variants:", len(V), "| train best:", best)
print("train gain by variant (%):")
print((tr.mean() / day_base.loc[TRAIN[0]:TRAIN[1]].mean() * 100).round(2).sort_values(ascending=False).head(8).to_string())
print("test gain by variant (%):")
print((te.mean() / day_base.loc[TEST:].mean() * 100).round(2).sort_values(ascending=False).head(8).to_string())
bw = base_in.loc[TEST:].mean(axis=1).groupby(pd.Grouper(freq="W-FRI")).transform("mean")
stress = bw[bw < 0.70].index
storm_te = storm.loc[TEST:][lambda x: x].index
b_in, b_is = V[best]
def cov(x, sl): return round(x.loc[sl].stack().mean() * 100, 1)
for lab, sl in (("test all", slice(TEST, None)), ("bad weeks", stress), ("storm days", storm_te)):
    print(f"{lab:10s} cover base {cov(base_in, sl)}  best {cov(b_in, sl)}")
for lab, (vi, _) in (("best", V[best]),):
    pass
down_miss_b = (r < -Z80 * s20).where(ok).loc[storm_te].stack().mean() * 100
print("storm days: baseline downside miss %.1f%%, upside miss %.1f%%" % (down_miss_b, (r > Z80 * s20).where(ok).loc[storm_te].stack().mean() * 100))
print("test HAC t:", round(newey_west_t_stat(te[best].values, lags=5), 2), "DSR:", deflated_sharpe_ratio(te[best].values, n_trials=len(V)))
print("PBO:", probability_of_backtest_overfitting(imp.loc[TRAIN[0]:].dropna().values, n_splits=16))
for y in range(2021, 2027):
    sl = slice(f"{y}-01-01", f"{y}-12-31")
    print(" ", y, cov(base_in, sl), cov(b_in, sl), "gain %.2f%%" % (te[best].loc[sl].mean() / day_base.loc[sl].mean() * 100))
print("storm days n:", len(storm_te), "bad-week days n:", len(stress), "data to", c.index[-1].date())

HOLD = ("2000-03-01", "2014-12-31")  # unseen by the pick (needs DATA=d00.pkl VIX=vix00.pkl)
ho = imp.loc[HOLD[0]:HOLD[1]].dropna()
if len(ho) > 250:
    hb = day_base.loc[HOLD[0]:HOLD[1]].mean()
    print("\nHOLDOUT 2000-2014, days", len(ho))
    print("holdout gain by variant (%):")
    print((ho.mean() / hb * 100).round(2).sort_values(ascending=False).head(8).to_string())
    print("best-train variant holdout gain %.2f%%, HAC t %.2f, DSR %s" % (ho[best].mean() / hb * 100,
          newey_west_t_stat(ho[best].values, lags=5), deflated_sharpe_ratio(ho[best].values, n_trials=len(V))["dsr"]))
    hs = storm.loc[HOLD[0]:HOLD[1]][lambda x: x].index
    hw = base_in.loc[HOLD[0]:HOLD[1]].mean(axis=1).groupby(pd.Grouper(freq="W-FRI")).transform("mean")
    hbad = hw[hw < 0.70].index
    for lab, sl in (("all", slice(*HOLD)), ("storm days", hs), ("bad weeks", hbad), ("2008-09", slice("2008-09-01", "2009-03-31"))):
        print(f"  {lab:10s} cover base {cov(base_in, sl)}  best {cov(b_in, sl)}")
    print("  storm days n", len(hs), "| baseline downside miss %.1f%%, upside miss %.1f%%" % (
        (r < -Z80 * s20).where(ok).loc[hs].stack().mean() * 100, (r > Z80 * s20).where(ok).loc[hs].stack().mean() * 100))
    for k in sorted(ho.columns, key=lambda k: -ho[k].mean())[:3]:
        print("  ", k, "holdout t %.2f" % newey_west_t_stat(ho[k].values, lags=5))
