import os
CACHE = os.environ.get('RESEARCH_CACHE', 'research_cache')  # pickles from fetch.py / sig10y.py
os.makedirs(CACHE, exist_ok=True)
import json, yfinance as yf, pandas as pd
s=open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'tickers.txt')).read().split()
tk=sorted(s)
tk=[t for t in tk if not t.endswith('-USD')]
m=yf.download(tk,period='60d',interval='5m',prepost=True,group_by='ticker',auto_adjust=False,threads=True,progress=False)
m.to_pickle(os.path.join(CACHE,'m5.pkl'))
d=yf.download(tk,period='1y',interval='1d',group_by='ticker',auto_adjust=False,threads=True,progress=False)
d.to_pickle(os.path.join(CACHE,'d1.pkl')); print(len(tk), m.shape, d.shape)
