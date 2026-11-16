import os
CACHE = os.environ.get('RESEARCH_CACHE', 'research_cache')  # pickles from fetch.py / sig10y.py
os.makedirs(CACHE, exist_ok=True)
import math, sys, numpy as np, pandas as pd
sys.path.insert(0,os.path.join(os.path.dirname(os.path.abspath(__file__)),'../../../../backend'))
from signals.stock_day_range import _pre_open_move, Z80, Z50, LADDER_P, INTRA_K, INTRA_REACH_K, _uncalibrate_reach
from statistics import NormalDist
df=pd.read_pickle(os.path.join(CACHE,'rows.pkl')).dropna(subset=['pre'])
days=sorted(df.day.unique()); cut=days[len(days)//2]
tr,te=df[df.day<cut],df[df.day>=cut]
mv={p:_pre_open_move(p) for p in LADDER_P}
def ev(x,anchor,k,j,name):
    a=x[anchor].values; s=x.sig.values; c=x.close.values
    lr=np.log(c/a); out={'n':len(x),'in80':np.mean(np.abs(lr)<=Z80*k*s)*100,'in50':np.mean(np.abs(lr)<=Z50*k*s)*100,
         'close_err%':np.mean(np.abs(c/a-1))*100}
    for p in LADDER_P:
        dip=a*np.exp(-j*mv[p]*s); pop=a*np.exp(j*mv[p]*s)
        out[f'dip{int(p*100)}']=np.mean(x.low.values<=dip)*100; out[f'pop{int(p*100)}']=np.mean(x.high.values>=pop)*100
    out['low_err50%']=np.median(np.abs(x.low.values/(a*np.exp(-j*mv[0.5]*s))-1))*100
    print(name, {k_:round(v,1) for k_,v in out.items()})
def fit(x,anchor):
    a=x[anchor].values; s=x.sig.values
    z=np.abs(np.log(x.close.values/a))/s
    k=np.quantile(z,0.8)/Z80
    # j: make 50% dip+pop hit average 50%
    best=None
    for j in np.arange(0.3,1.5,0.01):
        h=(np.mean(x.low.values<=a*np.exp(-j*mv[0.5]*s))+np.mean(x.high.values>=a*np.exp(j*mv[0.5]*s)))/2
        if best is None or abs(h-0.5)<best[0]: best=(abs(h-0.5),j)
    return k,best[1]
print('train',tr.day.min(),tr.day.max(),'test',te.day.min(),te.day.max())
ev(te,'prev',0.97,1.0,'A current (prev close)')
k,j=fit(tr,'pre'); print('fit pre k=%.3f j=%.3f'%(k,j)); ev(te,'pre',k,j,'B pre-market anchor')
kp,jp=fit(tr,'prev'); print('fit prev k=%.3f j=%.3f'%(kp,jp)); ev(te,'prev',kp,jp,'A2 prev refit')
# gap days only (|pre/prev-1|>1 sigma)
g=te[np.abs(np.log(te.pre/te.prev))>te.sig]
print('gap days',len(g)); ev(g,'prev',0.97,1.0,' A on gap days'); ev(g,'pre',k,j,' B on gap days')
# Intraday 10:00
left=1-30/390
for name,x in (('all',te),):
    a=x.last10.values; s=x.sig.values; sd=INTRA_K*s*math.sqrt(left); lr=np.log(x.close.values/a)
    print('10:00 close in80 %.1f in50 %.1f'%(np.mean(np.abs(lr)<=Z80*sd)*100,np.mean(np.abs(lr)<=Z50*sd)*100))
    for p in LADDER_P:
        m=INTRA_REACH_K*math.sqrt(left)*NormalDist().inv_cdf(1-_uncalibrate_reach(p)/2)
        dip=a*np.exp(-m*s)
        print(' 10:00 dip%d fwd-hit %.1f | day-low<=dip %.1f | dip above low-so-far %.1f'%(p*100,np.mean(x.lowrest.values<=dip)*100,np.mean(x.low.values<=dip)*100,np.mean(dip>x.low10.values)*100))
