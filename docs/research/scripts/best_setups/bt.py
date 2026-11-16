"""Best setups / full-go forward test on saved production EOD snapshots (what the model said that night).
Snapshots: GET /api/eod/snapshots/{date} saved to $RESEARCH_CACHE/snaps/<date>.json.
Prices: yfinance adjusted daily. Cost: 0.2% round trip. Excess = stock - SPY over the same sessions."""
import glob, json, os, pickle
import numpy as np, pandas as pd

C = os.environ.get("RESEARCH_CACHE", ".")
COST = 0.2
snaps = {}
for p in sorted(glob.glob(f"{C}/snaps/*.json")):
    try:
        d = json.load(open(p))
    except Exception:
        continue
    rows = d.get("run_results") or []
    if rows:
        snaps[os.path.basename(p)[:10]] = rows
dates = sorted(snaps)
tick = sorted({r["ticker"] for rs in snaps.values() for r in rs if r.get("ticker") and not r["ticker"].endswith("-USD")})
pk = f"{C}/px.pkl"
if os.path.exists(pk):
    px = pickle.load(open(pk, "rb"))
else:
    import yfinance as yf
    px = yf.download(tick + ["SPY"], start="2026-05-01", auto_adjust=True, progress=False, threads=True)
    pickle.dump(px, open(pk, "wb"))
cl, hi, lo = px["Close"], px["High"], px["Low"]
idx = [d.date().isoformat() for d in cl.index]
pos = {d: i for i, d in enumerate(idx)}


def fwd(t, d, h):
    if d not in pos or t not in cl:
        return None, 0
    i = pos[d]; j = min(i + h, len(idx) - 1)
    if j <= i:
        return None, 0
    a, b = cl[t].iloc[i], cl[t].iloc[j]
    s0, s1 = cl["SPY"].iloc[i], cl["SPY"].iloc[j]
    if not (a > 0 and b > 0):
        return None, 0
    return ((b / a - 1) * 100 - COST, (b / a - 1) * 100 - COST - (s1 / s0 - 1) * 100), j - i


def first_touch(t, d, tgt, stop, h=63):
    i = pos[d]; e = cl[t].iloc[i]
    for j in range(i + 1, min(i + h, len(idx) - 1) + 1):
        if lo[t].iloc[j] <= stop: return "stop", (stop / e - 1) * 100 - COST
        if hi[t].iloc[j] >= tgt: return "target", (tgt / e - 1) * 100 - COST
    j = min(i + h, len(idx) - 1)
    return ("open" if j - i < h else "expired"), (cl[t].iloc[j] / e - 1) * 100 - COST


def f(v):
    try: return float(v)
    except Exception: return None


groups = {
    "all": lambda r: True,
    "full_go": lambda r: r.get("entry_mode") == "full_go",
    "swing_list": lambda r: (r.get("entry_mode") == "full_go" and f(r.get("swing_entry_high")) and f(r.get("swing_stop"))
                             and f(r.get("swing_t1")) and (f(r.get("swing_rr")) or 0) >= 1.5
                             and f(r.get("swing_stop")) < f(r["close"]) <= f(r["swing_entry_high"]) * 1.03),
    "starter": lambda r: r.get("entry_mode") == "starter_only",
    "hard_lock": lambda r: r.get("entry_mode") == "hard_lock",
}


def nw_t(x, lag):
    x = np.asarray(x, float); n = len(x)
    if n < 3: return None
    e = x - x.mean(); v = e @ e / n
    for k in range(1, min(lag, n - 1) + 1):
        v += 2 * (1 - k / (lag + 1)) * (e[k:] @ e[:-k]) / n
    return x.mean() / np.sqrt(v / n) if v > 0 else None


out = {}
for h in (20, 60):
    print(f"\n=== {h} sessions (complete windows only), cost {COST}% ===")
    print(f"{'group':11} {'n':>5} {'avg%':>7} {'vsSPY':>7} {'beat%':>6} {'NW t':>6}")
    for g, fn in groups.items():
        rows, prev, by_day = [], set(), {}
        for d in dates:
            cur = {r["ticker"] for r in snaps[d] if fn(r)}
            for t in cur - prev if g != "all" else cur:
                ret, n = fwd(t, d, h)
                if ret is None or n < h: continue
                rows.append((d, t, *ret)); by_day.setdefault(d, []).append(ret[1])
            prev = cur
        if not rows:
            print(f"{g:11} {0:>5}"); continue
        a = np.array([r[2] for r in rows]); x = np.array([r[3] for r in rows])
        t = nw_t([np.mean(v) for _, v in sorted(by_day.items())], h)
        print(f"{g:11} {len(rows):>5} {a.mean():>+7.2f} {x.mean():>+7.2f} {100*(x>0).mean():>6.0f} {'-' if t is None else round(t,2):>6}")
        out[(g, h)] = rows
# swing-list first touch
ft, prev = [], set()
for d in dates:
    rs = {r["ticker"]: r for r in snaps[d] if groups["swing_list"](r)}
    for t in set(rs) - prev:
        if d in pos and t in cl:
            res, ret = first_touch(t, d, f(rs[t]["swing_t1"]), f(rs[t]["swing_stop"]))
            ft.append((d, t, res, ret))
    prev = set(rs)
df = pd.DataFrame(ft, columns=["date", "ticker", "result", "ret"])
print("\nSwing-list first touch (t1 vs stop, 63 sessions):")
print(df.groupby("result")["ret"].agg(["count", "mean"]).round(2))
df["month"] = df.date.str[:7]
print(df.groupby("month")["ret"].agg(["count", "mean"]).round(2))
pickle.dump({"rows": out, "first_touch": df}, open(f"{C}/bs_rows.pkl", "wb"))
