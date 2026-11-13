"""
Fama–French 5 factors + momentum (Ken French data library), regressed on the last year of daily returns.

Shows what the book is really betting on (e.g. "all high-momentum, low-value") and how much of its daily
moves those factors explain. Explanation and risk only — never an entry gate.
"""

from __future__ import annotations

import io
import logging
import time
import zipfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

_BASE = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
_FILES = {"ff5": "F-F_Research_Data_5_Factors_2x3_daily_CSV.zip", "mom": "F-F_Momentum_Factor_daily_CSV.zip"}
FACTORS = ["Mkt-RF", "SMB", "HML", "RMW", "CMA", "Mom"]
LABELS = {
    "Mkt-RF": "Market", "SMB": "Small size", "HML": "Value", "RMW": "Profitability (quality)",
    "CMA": "Conservative investment", "Mom": "Momentum",
}
CACHE_DAYS = 7
WINDOW = 252
MIN_OBS = 120
_mem: dict[str, Any] = {}


def parse_french_csv(text: str) -> pd.DataFrame:
    rows = []
    started = False
    for line in text.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if not started:
            started = len(parts) > 1 and parts[0] == "" and parts[1]
            cols = parts[1:] if started else None
            continue
        if not parts[0].isdigit() or len(parts[0]) != 8:
            if rows:
                break
            continue
        rows.append([parts[0]] + [float(x) for x in parts[1:]])
    df = pd.DataFrame(rows, columns=["date"] + cols).set_index("date")
    df.index = pd.to_datetime(df.index, format="%Y%m%d")
    return df.replace([-99.99, -999.0], np.nan) / 100.0


def load_factors(cache_dir: Path | None = None) -> pd.DataFrame | None:
    hit = _mem.get("df")
    if hit is not None and time.time() - _mem["ts"] < 86400:
        return hit
    import urllib.request

    if cache_dir is None:
        from config_loader import get_data_root

        cache_dir = get_data_root() / "ken_french"
    cache_dir.mkdir(parents=True, exist_ok=True)
    frames = []
    for key, fname in _FILES.items():
        p = cache_dir / f"{key}.csv"
        if not p.exists() or time.time() - p.stat().st_mtime > CACHE_DAYS * 86400:
            try:
                req = urllib.request.Request(_BASE + fname, headers={"User-Agent": "ThriveAlpha/1.0"})
                with urllib.request.urlopen(req, timeout=30) as r:
                    z = zipfile.ZipFile(io.BytesIO(r.read()))
                p.write_text(z.read(z.namelist()[0]).decode("latin-1"))
            except Exception as e:
                logger.warning("Ken French %s download failed: %s", key, e)
                if not p.exists():
                    return None
        frames.append(parse_french_csv(p.read_text()))
    df = frames[0].join(frames[1], how="inner")
    df.columns = [c.strip() for c in df.columns]
    _mem.update(df=df, ts=time.time())
    return df


def regress(excess: pd.Series, factors: pd.DataFrame) -> dict[str, Any] | None:
    d = factors[FACTORS].join(excess.rename("y"), how="inner").dropna().tail(WINDOW)
    if len(d) < MIN_OBS:
        return None
    X = np.column_stack([np.ones(len(d)), d[FACTORS].to_numpy()])
    y = d["y"].to_numpy()
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ coef
    r2 = 1 - float(resid.var()) / float(y.var()) if y.var() > 0 else 0.0
    return {
        "betas": {f: round(float(b), 2) for f, b in zip(FACTORS, coef[1:])},
        "alpha_ann_pct": round(float(coef[0]) * 252 * 100, 1),
        "r2": round(r2, 2),
        "n_days": len(d),
        "through": str(d.index[-1].date()),
    }


def _flags(b: dict[str, float]) -> list[str]:
    out = []
    if b.get("Mkt-RF", 1) >= 1.25:
        out.append(f"High market beta {b['Mkt-RF']:.2f}: a 10% S&P drop ≈ {b['Mkt-RF'] * 10:.0f}% for the book")
    if b.get("Mom", 0) >= 0.3:
        out.append("Heavy momentum bet: momentum crashes (e.g. 2009 rebound) would hit most holdings at once")
    if b.get("HML", 0) <= -0.3:
        out.append("Strong growth tilt (negative value): rising rates have historically hurt this mix")
    if b.get("SMB", 0) >= 0.3:
        out.append("Small-cap tilt: more volatile and less liquid than the S&P 500")
    if b.get("RMW", 0) <= -0.3:
        out.append("Low-profitability tilt: owns more unprofitable companies than the market")
    return out


def compute_ff_betas(per_holding: list[dict], factors: pd.DataFrame | None = None, prices: pd.DataFrame | None = None) -> dict[str, Any]:
    w = {h["ticker"]: float(h.get("pct") or 0) for h in per_holding if h.get("ticker") and (h.get("pct") or 0) > 0}
    if not w:
        return {}
    factors = factors if factors is not None else load_factors()
    if factors is None:
        return {"note": "Ken French factor data unavailable right now."}
    if prices is None:
        import yfinance as yf

        prices = yf.download(sorted(w), period="15mo", auto_adjust=True, progress=False)["Close"]
        if isinstance(prices, pd.Series):
            prices = prices.to_frame(sorted(w)[0])
    rets = prices.pct_change().dropna(how="all")
    rets.index = pd.to_datetime(rets.index).tz_localize(None).normalize()
    rf = factors["RF"]
    per = []
    for t in w:
        if t not in rets:
            continue
        r = regress(rets[t].dropna() - rf.reindex(rets.index).fillna(0), factors)
        if r:
            per.append({"ticker": t, "weight_pct": round(w[t], 1), **r})
    if not per:
        return {"note": "Not enough price history for factor betas."}
    tot = sum(p["weight_pct"] for p in per)
    book = {f: round(sum(p["betas"][f] * p["weight_pct"] for p in per) / tot, 2) for f in FACTORS}
    port = (rets[[p["ticker"] for p in per]].fillna(0) * [p["weight_pct"] / tot for p in per]).sum(axis=1)
    reg = regress(port - rf.reindex(port.index).fillna(0), factors) or {}
    return {
        "book_betas": book,
        "labels": LABELS,
        "r2": reg.get("r2"),
        "alpha_ann_pct": reg.get("alpha_ann_pct"),
        "through": reg.get("through"),
        "per_holding": sorted(per, key=lambda p: -p["weight_pct"]),
        "flags": _flags(book),
        "coverage_pct": round(tot, 1),
        "note": "Fama–French 5 factors + momentum, last 252 trading days. Betas near 0 = neutral; Market 1.0 = moves with the S&P. Explains risk only, never an entry gate.",
    }


_DAILY_MEMO: dict[tuple, dict[str, Any]] = {}


def compute_ff_betas_daily(per_holding: list[dict]) -> dict[str, Any]:
    """compute_ff_betas, memoised per day and holdings mix (warm refresh runs many times a day)."""
    from datetime import date as _date

    mix = tuple(sorted((h.get("ticker"), round(float(h.get("pct") or 0), 1)) for h in per_holding if h.get("ticker")))
    key = (_date.today().isoformat(), mix)
    if key not in _DAILY_MEMO:
        _DAILY_MEMO.clear()
        _DAILY_MEMO[key] = compute_ff_betas(per_holding)
    return _DAILY_MEMO[key]
