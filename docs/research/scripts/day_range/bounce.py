import os
CACHE = os.environ.get('RESEARCH_CACHE', 'research_cache')  # pickles from fetch.py / sig10y.py
os.makedirs(CACHE, exist_ok=True)
import math, numpy as np, pandas as pd
d=pd.read_pickle(os.path.join(CACHE,'d10.pkl'))
tks=sorted(set(d.columns.get_level_values(0)))
H=40; R=[]
for t in tks:
    try: x=d[t].dropna(subset=['Close'])
    except KeyError: continue
    if len(x)<400: continue
    c=x.Close.values.astype(float); l=x.Low.values.astype(float)
    lr=np.diff(np.log(c),prepend=np.nan); sig=pd.Series(lr).ewm(span=20).std().values
    hi252=pd.Series(c).rolling(252,min_periods=200).max().values
    ma50=pd.Series(c).rolling(50).mean().values
    fut_low=pd.Series(l[::-1]).rolling(H,min_periods=H).min().values[::-1]  # min low over [i, i+H-1]
    for i in range(252,len(c)-H-60):
        dd=c[i]/hi252[i]-1
        if dd<=-0.15 and c[i]<ma50[i] and sig[i]>0:
            b=np.min(l[i+1:i+1+H]); j=i+1+int(np.argmin(l[i+1:i+1+H]))
            R.append((t,x.index[i],dd,sig[i],c[i],b,c[min(i+60,len(c)-1)],c[min(j+60,len(c)-1)]/b-1, c[i+60]/c[i]-1))
df=pd.DataFrame(R,columns=['t','d','dd','sig','c','bot','c60','ret_from_bot','ret_now'])
df['y']=np.log(df.bot/df.c)/df.sig  # further fall, in daily sigmas
df['ddb']=pd.cut(df.dd,[-1,-0.4,-0.25,-0.15])
tr,te=df[df.d<'2021-01-01'],df[df.d>='2021-01-01']
print('events train',len(tr),'test',len(te),'tickers',df.t.nunique())
q=tr.groupby('ddb',observed=True).y.quantile([0.1,0.5,0.9]).unstack()
print(q.round(2))
te=te.join(q,on='ddb')
lo,mid,hi=[te.c*np.exp(te[k]*te.sig) for k in (0.1,0.5,0.9)]
inside=(te.bot>=lo)&(te.bot<=hi)
print('TEST 80%% zone coverage %.1f%%  zone width %.1f%% of price'%(inside.mean()*100,((hi-lo)/te.c).mean()*100))
print('median abs error of predicted bottom %.1f%% | naive (bottom=today) %.1f%% | actual further fall median %.1f%%'%(
  np.median(np.abs(te.bot/mid-1))*100,np.median(np.abs(te.bot/te.c-1))*100,np.median(te.bot/te.c-1)*100))
for k,name in ((0.5,'median zone'),(0.9,'top of zone')):
    lim=te.c*np.exp(te[k]*te.sig); fill=te.bot<=lim
    # return 60 days after buying at limit (approx: from limit to c60 of signal day+60) vs buy now
    r_lim=np.where(fill,te.c60/lim-1,np.nan)
    print(f'limit at {name}: filled {fill.mean()*100:.0f}% | avg 60d ret filled {np.nanmean(r_lim)*100:.1f}% vs buy-now {te.ret_now.mean()*100:.1f}% | missed trades buy-now ret {te.ret_now[~fill].mean()*100:.1f}%')
print('per year coverage', te.assign(i=inside).groupby(te.d.dt.year).i.mean().round(2).to_dict())
