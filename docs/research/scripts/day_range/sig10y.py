import os
CACHE = os.environ.get('RESEARCH_CACHE', 'research_cache')  # pickles from fetch.py / sig10y.py
os.makedirs(CACHE, exist_ok=True)
import math, sys, numpy as np, pandas as pd, yfinance as yf, json
sys.path.insert(0,os.path.join(os.path.dirname(os.path.abspath(__file__)),'../../../../backend'))
from signals.stock_day_range import ewma_sigmas, Z80, Z50
tks=sorted(set(pd.read_pickle(os.path.join(CACHE,'m5.pkl')).columns.get_level_values(0)))
try: d=pd.read_pickle(os.path.join(CACHE,'d10.pkl'))
except Exception:
    d=yf.download(tks,start='2015-06-01',interval='1d',group_by='ticker',auto_adjust=False,threads=True,progress=False); d.to_pickle(os.path.join(CACHE,'d10.pkl'))
def ewm_park(h,l,span):
    a=2/(span+1); out=[None]; v=None
    for i in range(1,len(h)):
        if h[i-1]>0 and l[i-1]>0:
            x=(math.log(h[i-1]/l[i-1]))**2/(4*math.log(2))
            v=x if v is None else (1-a)*v+a*x
        out.append(math.sqrt(v) if v else None)
    # out[i] = known after bar i-1? shift: make out[i] include bar i
    return out[1:]+[math.sqrt(v) if v else None]
R=[]
for t in tks:
    try: x=d[t].dropna(subset=['Close'])
    except KeyError: continue
    if len(x)<300: continue
    c=x.Close.values.astype(float); h=x.High.values.astype(float); l=x.Low.values.astype(float)
    s20=ewma_sigmas(list(c)); s10=ewma_sigmas(list(c),10); pk=ewm_park(h,l,20)
    for i in range(30,len(c)):
        if s20[i-1] and s10[i-1] and pk[i-1] and c[i-1]>0:
            R.append((x.index[i].year, x.index[i]>=pd.Timestamp('2026-08-24'), abs(math.log(c[i]/c[i-1])), s20[i-1], s10[i-1], pk[i-1]))
df=pd.DataFrame(R,columns=['y','recent','z','s20','s10','pk'])
df['blend']=np.sqrt((df.s20**2+df.pk**2)/2); df['mx']=np.maximum(df.s20,df.s10)
train=df[df.y<=2021]
for col in ['s20','s10','pk','blend','mx']:
    k=np.quantile(train.z/train[col],0.8)/Z80
    cov=lambda q: round(np.mean(q.z<=Z80*k*q[col])*100,1)
    byy=df.groupby('y').apply(cov)
    w=np.mean(2*Z80*k*df[col])*100
    print(f"{col:6s} k={k:.3f} test2022+={cov(df[df.y>=2022])} recent60d={cov(df[df.recent])} yrs min/max={byy.min()}/{byy.max()} avg width%={w:.2f}")
