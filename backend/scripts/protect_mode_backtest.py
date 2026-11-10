"""Protect-mode evidence: half position below the stock's own 200-day average (and when SPY is risk-off)
vs buy-and-hold of the same stock, over each stock's S&P 500 membership since 2000. Cash earns ^IRX.

    python scripts/protect_mode_backtest.py --ohlcv ohlcv2000.pkl   # yfinance Close for members + SPY + ^IRX
"""
import argparse, sys
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
ap = argparse.ArgumentParser(); ap.add_argument("--ohlcv", required=True); args = ap.parse_args()
from scripts.timing_rules_backtest import trend_sma, _metrics
from signals.alpha.core_satellite import regime_series
px=pd.read_pickle(args.ohlcv); C=px['Close']
irx=C['^IRX']; rf_all=(irx.ffill().bfill()/100/252).fillna(0.0)
m=pd.read_csv(ROOT / 'data/universe/sp500_membership.csv')
m['start_date']=pd.to_datetime(m.start_date); m['end_date']=pd.to_datetime(m.end_date).fillna(C.index[-1])
m['ticker']=m.ticker.str.replace('.','-',regex=False)
m=m[m.end_date>='2000-01-01']
cost=0.0015
PER={'2000-26':('2000-01-01','2026-12-31'),'2000-12':('2000-01-01','2012-12-31'),'2013-26':('2013-01-01','2026-12-31'),'2017-26':('2017-01-01','2026-12-31')}
rows=[]; bh_d={}; pr_d={}; sp_d={}; cover=[]
spy_on=regime_series(C['SPY'].dropna(),200,1.0).reindex(C.index).ffill().fillna(1.0)
for t,g in m.groupby('ticker'):
    if t not in C or C[t].notna().sum()<400: 
        cover.append((t,False)); continue
    cover.append((t,True))
    c=C[t].dropna(); w=(0.5+0.5*trend_sma(c,200)).shift(1).fillna(1.0)
    ret=c.pct_change().fillna(0.0); rf=rf_all.reindex(c.index).fillna(0.0)
    strat=w*ret+(1-w)*rf-w.diff().abs().fillna(0.0)*cost
    ws=(0.5+0.5*spy_on.reindex(c.index).ffill().fillna(1.0)).shift(1).fillna(1.0)
    sstrat=ws*ret+(1-ws)*rf-ws.diff().abs().fillna(0.0)*cost
    mask=pd.Series(False,index=c.index)
    for _,r in g.iterrows(): mask|=(c.index>=max(r.start_date,pd.Timestamp('2000-01-01')))&(c.index<=r.end_date)
    bh_d[t]=ret.where(mask); pr_d[t]=strat.where(mask); sp_d[t]=sstrat.where(mask)
    for p,(a,b) in PER.items():
        sl=mask&(c.index>=a)&(c.index<=b)
        if sl.sum()<252: continue
        mb=_metrics(ret[sl],rf[sl]); ms=_metrics(strat[sl],rf[sl]); mq=_metrics(sstrat[sl],rf[sl])
        if mb and ms: rows.append(dict(t=t,per=p,bh_cagr=mb['cagr'],pr_cagr=ms['cagr'],bh_dd=mb['max_dd'],pr_dd=ms['max_dd'],sp_cagr=mq['cagr'],sp_dd=mq['max_dd']))
r=pd.DataFrame(rows)
cv=pd.DataFrame(cover,columns=['t','ok']); print('tickers with data',cv.ok.sum(),'of',len(cv))
mem0=m[(m.start_date<='2000-01-03')]; print('2000-01-03 members with data', mem0.ticker.isin(cv[cv.ok].t).sum(),'of',len(mem0))
BH=pd.DataFrame(bh_d); PR=pd.DataFrame(pr_d)
for p,(a,b) in PER.items():
    x=r[r.per==p]
    bh=BH.loc[a:b].mean(axis=1).dropna(); pr=PR.loc[a:b].mean(axis=1).dropna(); rf=rf_all.reindex(bh.index).fillna(0)
    eb=_metrics(bh,rf); ep=_metrics(pr,rf)
    print(f"\n{p}: n={len(x)} | median stock: CAGR {x.bh_cagr.median():.1f}% -> {x.pr_cagr.median():.1f}%, worst drop {x.bh_dd.median():.0f}% -> {x.pr_dd.median():.0f}%, smaller drop {100*(x.pr_dd>x.bh_dd).mean():.0f}%, higher CAGR {100*(x.pr_cagr>x.bh_cagr).mean():.0f}% | SPY-risk-off half: CAGR {x.sp_cagr.median():.1f}%, drop {x.sp_dd.median():.0f}%")
    print(f"   equal-weight members: CAGR {eb['cagr']:.1f}% -> {ep['cagr']:.1f}%, max DD {eb['max_dd']:.0f}% -> {ep['max_dd']:.0f}%, avg names/day {BH.loc[a:b].notna().sum(axis=1).mean():.0f}")
