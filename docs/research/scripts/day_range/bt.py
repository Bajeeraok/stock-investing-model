import os
CACHE = os.environ.get('RESEARCH_CACHE', 'research_cache')  # pickles from fetch.py / sig10y.py
os.makedirs(CACHE, exist_ok=True)
import math, sys, numpy as np, pandas as pd
sys.path.insert(0,os.path.join(os.path.dirname(os.path.abspath(__file__)),'../../../../backend'))
from signals.stock_day_range import ewma_sigmas, _pre_open_move, Z80, Z50, CLOSE_K, LADDER_P, INTRA_K, INTRA_REACH_K, _uncalibrate_reach
from statistics import NormalDist
m=pd.read_pickle(os.path.join(CACHE,'m5.pkl')); d=pd.read_pickle(os.path.join(CACHE,'d1.pkl'))
tks=sorted(set(m.columns.get_level_values(0)))
rows=[]
for t in tks:
    try:
        dc=d[t]['Close'].dropna()
        x=m[t].dropna(subset=['Close'])
    except KeyError: continue
    if len(dc)<60 or x.empty: continue
    x=x.tz_convert('America/New_York') if x.index.tz is not None else x
    di=[i.date() for i in dc.index]; closes=list(dc.values.astype(float))
    sig=ewma_sigmas(closes)
    pos={dd:i for i,dd in enumerate(di)}
    for day,g in x.groupby(x.index.date):
        i=pos.get(day)
        if i is None or i<30 or sig[i-1] is None: continue
        hm=g.index.hour*60+g.index.minute
        reg=g[(hm>=570)&(hm<960)]; pre=g[(hm>=240)&(hm<565)]
        if len(reg)<70: continue
        a10=reg[(reg.index.hour*60+reg.index.minute)<600]  # 9:30-10:00 bars
        rows.append(dict(t=t,day=day,prev=closes[i-1],sig=sig[i-1],pre=float(pre['Close'].iloc[-1]) if len(pre) else np.nan,
            open=float(reg['Open'].iloc[0]),low=float(reg['Low'].min()),high=float(reg['High'].max()),close=closes[i],
            last10=float(a10['Close'].iloc[-1]),low10=float(a10['Low'].min()),high10=float(a10['High'].max()),
            lowrest=float(reg[(reg.index.hour*60+reg.index.minute)>=600]['Low'].min()),highrest=float(reg[(reg.index.hour*60+reg.index.minute)>=600]['High'].max())))
df=pd.DataFrame(rows); df.to_pickle(os.path.join(CACHE,'rows.pkl'))
print(len(df), df.t.nunique(), df.day.min(), df.day.max(), 'pre missing', df.pre.isna().mean().round(3))
