"""Post-earnings move: how well can we predict size and direction? Train < 2021, test 2021+."""
import os, sys, pickle, math
import numpy as np, pandas as pd
CACHE = os.environ.get('RESEARCH_CACHE', 'research_cache')
d = pd.read_pickle(os.path.join(CACHE, 'd10.pkl')); er = pickle.load(open(os.path.join(CACHE, 'er.pkl'), 'rb'))
spy = d['SPY'].dropna(subset=['Close']) if 'SPY' in d.columns.get_level_values(0) else None
R = []
for t, e in er.items():
    try: x = d[t].dropna(subset=['Close'])
    except KeyError: continue
    if len(x) < 300: continue
    idx = x.index.tz_localize(None) if x.index.tz is not None else x.index
    dates = idx.normalize(); c = x.Close.values.astype(float); o = x.Open.values.astype(float)
    lr = np.diff(np.log(c), prepend=np.nan); sig = pd.Series(lr).ewm(span=20).std().values
    ma50 = pd.Series(c).rolling(50).mean().values
    rows = []
    for ts, rec in e.iterrows():
        if pd.isna(rec.get('Reported EPS')): continue
        h = ts.hour; D = pd.Timestamp(ts.date())
        if h >= 12: pre = dates.searchsorted(D, side='right') - 1; react = pre + 1   # after close
        elif 4 <= h < 10: react = dates.searchsorted(D, side='left'); pre = react - 1  # before open
        else: continue
        if pre < 60 or react + 21 >= len(c) or dates[pre] > D: continue
        if h < 12 and dates[react] != D: continue
        if h >= 12 and dates[pre] != D: continue
        m = c[react] / c[pre] - 1; g = o[react] / c[pre] - 1
        if abs(m) > 0.6: continue  # split / bad print
        old = c[min(react + 1, len(c) - 1)] / c[react - 1] - 1 if h >= 12 else c[react + 1] / c[react] - 1  # current app's window
        rows.append(dict(t=t, d=D, move=m, gap=g, old_window=old, sig=sig[pre], ret20=c[pre] / c[pre - 20] - 1,
                         ret60=c[pre] / c[pre - 60] - 1, above50=c[pre] > ma50[pre], surprise=rec.get('Surprise(%)'),
                         drift20=c[react + 20] / c[react] - 1))
    rows.sort(key=lambda r: r['d'])
    for i, r in enumerate(rows):
        past = [abs(z['move']) for z in rows[max(0, i - 8):i]]
        r['n_past'] = len(past)
        r['mean6'] = np.mean(past[-6:]) if past else np.nan
        r['med8'] = np.median(past) if past else np.nan
        r['last_move'] = rows[i - 1]['move'] if i else np.nan
        r['last_surprise'] = rows[i - 1]['surprise'] if i else np.nan
        R.append(r)
df = pd.DataFrame(R); df['am'] = df.move.abs(); df['up'] = df.move > 0
df = df[df.n_past >= 4].copy()
tr, te = df[df.d < '2021-01-01'], df[df.d >= '2021-01-01']
print(f'events {len(df)} (train {len(tr)}, test {len(te)}), tickers {df.t.nunique()}, median |move| {df.am.median()*100:.1f}%')
print(f'gap vs close: median |gap| {df.gap.abs().median()*100:.1f}%, same sign as close {np.mean(np.sign(df.gap)==np.sign(df.move))*100:.0f}%')
print(f'current app window (wrong day for pre-market reporters): corr with true move {np.corrcoef(df.old_window, df.move)[0,1]:.2f}')

print('\n== SIZE (test 2021+) ==')
preds = {'sigma20 x k': 'sig', 'mean last 6 (app)': 'mean6', 'median last 8': 'med8'}
for name, col in preds.items():
    k = np.median(tr.am) / np.median(tr[col]); p = te[col] * k
    q80 = np.quantile(tr.am / (tr[col] * k), 0.8); q50 = np.quantile(tr.am / (tr[col] * k), 0.5)
    cov80 = np.mean(te.am <= q80 * p); cov50 = np.mean(te.am <= q50 * p)
    print(f'{name:20s} k={k:.2f} median abs err {np.median(np.abs(te.am-p))*100:.2f}% | corr {np.corrcoef(p, te.am)[0,1]:.2f} | 80% band ±{q80:.2f}x -> {cov80*100:.0f}% | 50% ±{q50:.2f}x -> {cov50*100:.0f}% | band width 80% median ±{np.median(q80*p)*100:.1f}%')
blend = lambda x: 0.5 * x.med8 / np.median(tr.med8) * np.median(tr.am) + 0.5 * x.sig / np.median(tr.sig) * np.median(tr.am)
pb = blend(te); q80 = np.quantile(tr.am / blend(tr), 0.8)
print(f'{"blend":20s} median abs err {np.median(np.abs(te.am-pb))*100:.2f}% | corr {np.corrcoef(pb, te.am)[0,1]:.2f} | 80% ±{q80:.2f}x -> {np.mean(te.am<=q80*pb)*100:.0f}%')
print('naive: everyone gets train median', f'{np.median(np.abs(te.am-np.median(tr.am)))*100:.2f}%')
print('coverage by year (median last 8, 80%):', te.assign(i=te.am <= np.quantile(tr.am/(tr.med8*np.median(tr.am)/np.median(tr.med8)),0.8)*te.med8*np.median(tr.am)/np.median(tr.med8)).groupby(te.d.dt.year).i.mean().round(2).to_dict())

print('\n== DIRECTION (all years; base rate up) ==')
print(f'up base rate train {tr.up.mean()*100:.1f}%, test {te.up.mean()*100:.1f}%')
def dir_test(name, s):
    for nm, x in (('train', tr), ('test', te)):
        v = s(x); ok = v.notna()
        x2, v2 = x[ok], v[ok].astype(bool)
        hit = np.mean(v2 == x2.up); n = len(x2)
        a, b = x2.move[v2], x2.move[~v2]
        se = math.sqrt(a.var() / len(a) + b.var() / len(b)) if len(a) > 2 and len(b) > 2 else np.nan
        print(f'  {name:32s} {nm:5s} n={n:5d} hit {hit*100:.1f}% | avg move when says up {a.mean()*100:+.2f}% vs down {b.mean()*100:+.2f}% | t={(a.mean()-b.mean())/se:.2f}')
dir_test('pre-ER 20d drift > 0', lambda x: x.ret20 > 0)
dir_test('60d momentum > 0', lambda x: x.ret60 > 0)
dir_test('above 50-day', lambda x: x.above50)
dir_test('last ER moved up', lambda x: (x.last_move > 0).where(x.last_move.notna()))
dir_test('last quarter beat (surprise>0)', lambda x: (x.last_surprise > 0).where(x.last_surprise.notna()))

print('\n== AFTER THE REACTION: drift day 1 -> 20 by reaction sign (test) ==')
for nm, x in (('train', tr), ('test', te)):
    a, b = x.drift20[x.up], x.drift20[~x.up]
    se = math.sqrt(a.var()/len(a)+b.var()/len(b))
    print(f'  {nm}: after up reaction {a.mean()*100:+.2f}% (n={len(a)}), after down {b.mean()*100:+.2f}% (n={len(b)}), t={(a.mean()-b.mean())/se:.2f}')
df.to_pickle(os.path.join(CACHE, 'er_rows.pkl'))
