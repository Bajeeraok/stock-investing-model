import os
CACHE = os.environ.get('RESEARCH_CACHE', 'research_cache')  # pickles from fetch.py / sig10y.py
os.makedirs(CACHE, exist_ok=True)
import math, sys, numpy as np, pandas as pd
sys.path.insert(0,os.path.join(os.path.dirname(os.path.abspath(__file__)),'../../../../backend'))
from signals.stock_day_range import _pre_open_move, Z80, Z50, LADDER_P, INTRA_K
df=pd.read_pickle(os.path.join(CACHE,'rows.pkl')).dropna(subset=['pre'])
days=sorted(df.day.unique()); cut=days[len(days)//2]
mv={p:_pre_open_move(p) for p in LADDER_P}
left=1-30/390
for name,x in (('first half',df[df.day<cut]),('second half',df[df.day>=cut]),('all 60d',df)):
    zp=np.abs(np.log(x.close/x.pre))/x.sig; zv=np.abs(np.log(x.close/x.prev))/x.sig
    zi=np.abs(np.log(x.close/x.last10))/(x.sig*math.sqrt(left))
    # j such that low/high touch rates match ladder p on average across p
    def jfit(a):
        best=None
        for j in np.arange(0.4,1.6,0.01):
            e=sum(abs((np.mean(x.low<=x[a]*np.exp(-j*mv[p]*x.sig))+np.mean(x.high>=x[a]*np.exp(j*mv[p]*x.sig)))/2-p) for p in LADDER_P)
            if best is None or e<best[0]: best=(e,j)
        return best[1]
    print(f"{name}: n={len(x)} k_pre={np.quantile(zp,.8)/Z80:.3f} k_prev={np.quantile(zv,.8)/Z80:.3f} j_pre={jfit('pre'):.2f} j_prev={jfit('prev'):.2f} k_intra10={np.quantile(zi,.8)/Z80:.3f} (now {INTRA_K})")
# NVDA-like check: NVDA rows
n=df[df.t=='NVDA']; print('NVDA days',len(n))
