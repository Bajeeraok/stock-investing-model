"""Does scaling the day-range width by a VIX signal improve the 80% close range?
Baseline: |log(C_t/C_t-1)| inside ±Z80·CLOSE_K·σ_EWMA(t-1). Variant: σ × clip(f(t-1)^a, lo, 3).
Score: interval score (lower = better), coverage overall / stress weeks / calm days.
Train 2016–2020 picks a; 20-session embargo; test 2021+. Data: dr_bt/d10.pkl, dr_bt/vix.pkl."""
import sys, itertools
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "backend"))
from signals.stock_day_range import ewma_sigmas, Z80, CLOSE_K
from signals.statistical_validation import newey_west_t_stat, deflated_sharpe_ratio, probability_of_backtest_overfitting

D = Path("/home/ubuntu/dr_bt")
d = pd.read_pickle(D / "d10.pkl")
c = d.xs("Close", axis=1, level="Price").sort_index()
v = pd.read_pickle(D / "vix.pkl").reindex(c.index).ffill()
sig = pd.DataFrame({t: ewma_sigmas(list(c[t].ffill().values)) for t in c.columns}, index=c.index).astype(float)
sig[c.isna()] = np.nan
r = np.log(c / c.shift(1))
sp = sig.shift(1) * CLOSE_K            # known before day t
vix, v3 = v["^VIX"], v["^VIX3M"]
spy = sig["SPY"] if "SPY" in sig else sig.median(axis=1)
feats = {
    "vix_vs_20d": vix / vix.rolling(20).mean(),
    "vix_vs_vix3m": vix / v3,
    "vix_vs_spy_vol": (vix / 100 / np.sqrt(252)) / spy,
}
feats = {k: f.shift(1) for k, f in feats.items()}   # value at the prior close
ok = r.notna() & sp.notna()
TRAIN, TEST = ("2016-01-01", "2020-12-31"), "2021-02-01"  # ~20-session embargo

def evaluate(scale: pd.Series | None):
    s = sp if scale is None else sp.mul(scale, axis=0)
    hw = Z80 * s
    a = r.abs()
    inside = (a <= hw).where(ok)
    isc = (2 * hw + (2 / 0.2) * (a - hw).clip(lower=0)).where(ok)
    return inside, isc

base_in, base_is = evaluate(None)
variants = {}
for (name, f), a, lo in itertools.product(feats.items(), (0.25, 0.5, 0.75, 1.0, 1.5, 2.0), (1.0, 0.7)):
    sc = (f ** a).clip(lo, 3.0).fillna(1.0)
    variants[(name, a, lo)] = evaluate(sc)

day_base = base_is.mean(axis=1)
imp = pd.DataFrame({k: day_base - isc.mean(axis=1) for k, (_, isc) in variants.items()})  # >0 = better
tr, te = imp.loc[TRAIN[0]:TRAIN[1]].dropna(), imp.loc[TEST:].dropna()
best = tr.mean().idxmax()
print("variants:", len(variants), "| train best:", best, "train IS gain %.3f%%" % (tr[best].mean() / day_base.loc[TRAIN[0]:TRAIN[1]].mean() * 100))

def summary(label, inside, isc, sl):
    x_in, x_is = inside.loc[sl].stack(), isc.loc[sl].stack()
    return f"{label:10s} cover80 {x_in.mean()*100:5.1f}%  IS {x_is.mean()*100:.3f}"

bw = base_in.loc[TEST:].mean(axis=1).groupby(pd.Grouper(freq="W-FRI")).transform("mean")
stress_days = bw[bw < 0.70].index
calm_days = feats["vix_vs_20d"].loc[TEST:][lambda s: s < 0.95].index
b_in, b_is = variants[best]
for lab, sl in (("test all", slice(TEST, None)), ("stress wks", stress_days), ("calm days", calm_days)):
    print(lab, "|", summary("baseline", base_in, base_is, sl), "|", summary("vix", b_in, b_is, sl))
print("mean half-width test: base %.2f%%  vix %.2f%%" % (
    (Z80 * sp).loc[TEST:].stack().mean() * 100,
    (Z80 * sp.mul((feats[best[0]] ** best[1]).clip(best[2], 3).fillna(1), axis=0)).loc[TEST:].stack().mean() * 100))
print("by year coverage (base / vix):")
for y in range(2021, 2027):
    sl = slice(f"{y}-01-01", f"{y}-12-31")
    print(" ", y, round(base_in.loc[sl].stack().mean() * 100, 1), round(b_in.loc[sl].stack().mean() * 100, 1),
          "IS gain %.2f%%" % (te[best].loc[sl].mean() / day_base.loc[sl].mean() * 100))
print("test HAC t (daily IS gain, lags 5):", round(newey_west_t_stat(te[best].values, lags=5), 2))
print("DSR:", deflated_sharpe_ratio(te[best].values, n_trials=len(variants)))
print("PBO (all variants, full period):", probability_of_backtest_overfitting(imp.loc[TRAIN[0]:].dropna().values, n_splits=16))
print("stress days n:", len(stress_days), "calm days n:", len(calm_days))
