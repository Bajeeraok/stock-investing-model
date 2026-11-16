import os, pickle, time
import yfinance as yf
CACHE = os.environ.get('RESEARCH_CACHE', 'research_cache'); os.makedirs(CACHE, exist_ok=True)
here = os.path.dirname(os.path.abspath(__file__))
tks = open(os.path.join(here, '../day_range/tickers.txt')).read().split()
out = {}
for t in tks:
    for a in range(3):
        try:
            e = yf.Ticker(t).get_earnings_dates(limit=48)
            if e is not None and not e.empty:
                out[t] = e
            break
        except Exception:
            time.sleep(2)
pickle.dump(out, open(os.path.join(CACHE, 'er.pkl'), 'wb')); print(len(out), 'tickers with earnings dates')
