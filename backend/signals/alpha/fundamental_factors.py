"""
Point-in-time fundamental factors from SEC EDGAR XBRL ``companyfacts`` (free, no key).

Every fact carries the date it was ``filed``, so a factor "as of" day D only uses filings
with ``filed <= D`` — no look-ahead, unlike vendor snapshots of restated financials.

Factors (higher = more attractive):
  sue           standardized unexpected earnings: (EPS_q - EPS_q-4) / std of last 8 YoY diffs
  rev_growth    TTM revenue / TTM revenue one year earlier - 1
  gross_prof    TTM gross profit / total assets (Novy-Marx)
  roa           TTM net income / total assets
  low_accruals  -(TTM net income - TTM operating cash flow) / total assets (Sloan)
  fund_score    mean cross-sectional percentile of the above (computed by ``add_fund_score``)
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

SEC_UA = "ThriveAlpha research (contact via repo owner)"
FACTORS = ("sue", "rev_growth", "gross_prof", "roa", "low_accruals")

CONCEPTS: dict[str, tuple[str, ...]] = {
    "eps": ("EarningsPerShareDiluted", "EarningsPerShareBasic"),
    "revenue": (
        "Revenues",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "SalesRevenueNet",
        "RevenuesNetOfInterestExpense",
    ),
    "gross_profit": ("GrossProfit",),
    "net_income": ("NetIncomeLoss", "ProfitLoss"),
    "cfo": (
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    ),
    "assets": ("Assets",),
}
_INSTANT = {"assets"}


def _facts_rows(facts: dict, concept: str) -> list[dict]:
    units = ((facts.get("facts") or {}).get("us-gaap") or {}).get(concept, {}).get("units") or {}
    for key in ("USD/shares", "USD"):
        if key in units:
            return units[key]
    return []


def _quarterly_flow(rows: list[dict]) -> pd.DataFrame:
    """3-month values per fiscal period end, with the earliest filing date for each.

    10-Q cash-flow facts are year-to-date and Q4 usually only exists inside the 10-K
    annual figure, so missing quarters are derived by differencing cumulative durations.
    """
    recs = []
    for r in rows:
        if not r.get("start") or not r.get("end") or r.get("val") is None or not r.get("filed"):
            continue
        s, e = pd.Timestamp(r["start"]), pd.Timestamp(r["end"])
        recs.append((s, e, (e - s).days, float(r["val"]), pd.Timestamp(r["filed"])))
    if not recs:
        return pd.DataFrame(columns=["end", "val", "filed"])
    df = pd.DataFrame(recs, columns=["start", "end", "days", "val", "filed"])
    df = df.sort_values("filed").drop_duplicates(["start", "end"], keep="first")

    out: dict[pd.Timestamp, tuple[float, pd.Timestamp]] = {}
    for r in df[(df.days >= 80) & (df.days <= 100)].itertuples():
        out[r.end] = (r.val, r.filed)
    cum = df[df.days > 100].sort_values(["start", "end"])
    for _, g in cum.groupby("start"):
        g = g.sort_values("end")
        prev_end, prev_val = None, None
        # the first ~3-month stretch of a fiscal year is a plain quarter
        q1 = df[(df.start == g.start.iloc[0]) & (df.days >= 80) & (df.days <= 100)]
        if not q1.empty:
            prev_end, prev_val = q1.end.iloc[0], q1.val.iloc[0]
        for r in g.itertuples():
            if prev_end is not None and 80 <= (r.end - prev_end).days <= 100 and r.end not in out:
                out[r.end] = (r.val - prev_val, r.filed)
            prev_end, prev_val = r.end, r.val
    q = pd.DataFrame([(e, v, f) for e, (v, f) in out.items()], columns=["end", "val", "filed"])
    return q.sort_values("end").reset_index(drop=True)


def _instant(rows: list[dict]) -> pd.DataFrame:
    recs = [
        (pd.Timestamp(r["end"]), float(r["val"]), pd.Timestamp(r["filed"]))
        for r in rows if r.get("end") and r.get("val") is not None and r.get("filed")
    ]
    if not recs:
        return pd.DataFrame(columns=["end", "val", "filed"])
    df = pd.DataFrame(recs, columns=["end", "val", "filed"])
    return df.sort_values("filed").drop_duplicates("end", keep="first").sort_values("end").reset_index(drop=True)


def parse_companyfacts(facts: dict) -> dict[str, pd.DataFrame]:
    """Per concept: DataFrame(end, val, filed); the first concept alias with data wins."""
    out: dict[str, pd.DataFrame] = {}
    for name, aliases in CONCEPTS.items():
        # Filers switch tags over time (e.g. Revenues -> RevenueFromContract... after ASC 606),
        # so stitch aliases together, earlier aliases winning on the same period end.
        parts = []
        for c in aliases:
            rows = _facts_rows(facts, c)
            if rows:
                parts.append(_instant(rows) if name in _INSTANT else _quarterly_flow(rows))
        if parts:
            df = pd.concat(parts, ignore_index=True).drop_duplicates("end", keep="first")
            out[name] = df.sort_values("end").reset_index(drop=True)
        else:
            out[name] = pd.DataFrame(columns=["end", "val", "filed"])
    return out


def _known(df: pd.DataFrame, as_of: pd.Timestamp) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    k = df[df.filed <= as_of]
    return k.sort_values("end")


def _ttm(df: pd.DataFrame, lag: int = 0) -> float | None:
    """Sum of 4 consecutive quarters ending ``lag`` quarters before the latest one."""
    if df is None or len(df) < 4 + lag:
        return None
    w = df.iloc[len(df) - 4 - lag: len(df) - lag]
    span = (w.end.iloc[-1] - w.end.iloc[0]).days
    if not 250 <= span <= 300:
        return None
    return float(w.val.sum())


def factors_as_of(parsed: dict[str, pd.DataFrame], as_of: Any) -> dict[str, float | None]:
    d = pd.Timestamp(as_of)
    k = {n: _known(df, d) for n, df in parsed.items()}
    out: dict[str, float | None] = {f: None for f in FACTORS}
    out["days_since_filing"] = None

    eps = k.get("eps")
    if eps is not None and len(eps) >= 5:
        s = eps.set_index("end").val
        yoy = []
        for end, v in s.items():
            prior = s[(s.index >= end - pd.Timedelta(days=380)) & (s.index <= end - pd.Timedelta(days=350))]
            if len(prior):
                yoy.append((end, v - prior.iloc[-1]))
        if len(yoy) >= 4:
            diffs = np.array([x for _, x in yoy[-8:]])
            sd = diffs.std(ddof=1) if len(diffs) > 1 else 0.0
            if sd > 1e-9:
                out["sue"] = float(np.clip(diffs[-1] / sd, -10, 10))
        out["days_since_filing"] = float((d - eps.filed.max()).days)

    rev = k.get("revenue")
    r0, r1 = _ttm(rev), _ttm(rev, lag=4)
    if r0 is not None and r1 and r1 > 0:
        out["rev_growth"] = r0 / r1 - 1

    assets = k.get("assets")
    a = float(assets.val.iloc[-1]) if assets is not None and len(assets) else None
    if a and a > 0:
        gp, ni, cfo = _ttm(k.get("gross_profit")), _ttm(k.get("net_income")), _ttm(k.get("cfo"))
        if gp is not None:
            out["gross_prof"] = gp / a
        if ni is not None:
            out["roa"] = ni / a
        if ni is not None and cfo is not None:
            out["low_accruals"] = -(ni - cfo) / a
    return out


def add_fund_score(df: pd.DataFrame, date_col: str = "as_of_date", min_factors: int = 2) -> pd.DataFrame:
    """Per-date percentile ranks of each factor, averaged into ``fund_score`` (0–100)."""
    pct = df.groupby(date_col)[list(FACTORS)].rank(pct=True)
    n = pct.notna().sum(axis=1)
    df = df.copy()
    df["fund_score"] = (pct.mean(axis=1) * 100).where(n >= min_factors)
    return df


def load_cik_map(cache_dir: Path, user_agent: str = SEC_UA, refresh: bool = False) -> dict[str, int]:
    import requests

    p = cache_dir / "company_tickers.json"
    if refresh or not p.exists():
        r = requests.get("https://www.sec.gov/files/company_tickers.json", headers={"User-Agent": user_agent}, timeout=30)
        r.raise_for_status()
        p.write_text(r.text)
    raw = json.loads(p.read_text())
    return {str(v["ticker"]).upper().replace("-", "."): int(v["cik_str"]) for v in raw.values()}


def fetch_companyfacts(cik: int, cache_dir: Path, user_agent: str = SEC_UA, max_age_days: float = 7.0) -> dict | None:
    import requests

    p = cache_dir / f"CIK{cik:010d}.json"
    if p.exists() and (time.time() - p.stat().st_mtime) < max_age_days * 86400:
        try:
            return json.loads(p.read_text())
        except Exception:
            pass
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
    for attempt in range(3):
        r = requests.get(url, headers={"User-Agent": user_agent}, timeout=60)
        if r.status_code == 404:
            return None
        if r.status_code == 200:
            p.write_text(r.text)
            return r.json()
        time.sleep(1.0 + attempt)
    return None
