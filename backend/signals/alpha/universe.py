"""
Survivorship-aware S&P 500 universe from Wikipedia's constituent and change tables.

Builds ``ticker,start_date,end_date,sector`` ranges (the format used by
signals/backtest_universe.py). Tickers removed from the index keep their membership
window, so a backtest on date D only uses stocks that were members on D. Price history
for many delisted names is not on free sources; that residual bias is documented.
"""
from __future__ import annotations

from io import StringIO
from pathlib import Path

import pandas as pd

BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_MEMBERSHIP_CSV = BACKEND_ROOT / "data" / "universe" / "sp500_membership.csv"
WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
# MIT-licensed historical S&P 500 membership ranges (github.com/fja05680/sp500).
HISTORY_URL = "https://raw.githubusercontent.com/fja05680/sp500/master/sp500_ticker_start_end.csv"
EARLIEST = "1990-01-01"


def _norm(t: str) -> str:
    return str(t).strip().upper().replace(".", "-")


def _flatten(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [" ".join(str(x) for x in c if "Unnamed" not in str(x)).strip() for c in df.columns]
    return df


def _is_changes_table(df: pd.DataFrame) -> bool:
    cols = " ".join(str(c).lower() for c in _flatten(df.copy()).columns)
    return "added" in cols and "removed" in cols


def membership_from_tables(current: pd.DataFrame, changes: pd.DataFrame | None) -> pd.DataFrame:
    """Combine current constituents and the dated add/remove log into membership ranges.

    With ``changes=None`` only current members are returned (start = date added); removed
    names are then missing, which re-introduces survivorship bias — callers should warn.
    """
    current = _flatten(current.copy())
    if changes is None:
        changes = pd.DataFrame({"Date": [], "Added Ticker": [], "Removed Ticker": []})
    changes = _flatten(changes.copy())
    sym_col = next(c for c in current.columns if c.lower().startswith("symbol"))
    sec_col = next((c for c in current.columns if "sector" in c.lower()), None)
    add_col = next((c for c in current.columns if "added" in c.lower()), None)
    date_col = next(c for c in changes.columns if c.lower().startswith("date") or c.lower().startswith("effective"))
    added_col = next(c for c in changes.columns if "added" in c.lower() and "ticker" in c.lower())
    removed_col = next(c for c in changes.columns if "removed" in c.lower() and "ticker" in c.lower())

    ch = changes[[date_col, added_col, removed_col]].copy()
    ch.columns = ["date", "added", "removed"]
    ch["date"] = pd.to_datetime(ch["date"], errors="coerce")
    ch = ch.dropna(subset=["date"]).sort_values("date")

    sector = {}
    rows = []
    for _, r in current.iterrows():
        t = _norm(r[sym_col])
        if sec_col:
            sector[t] = r[sec_col]
        start = pd.to_datetime(r[add_col], errors="coerce") if add_col else pd.NaT
        rows.append({"ticker": t, "start_date": start if pd.notna(start) else pd.Timestamp(EARLIEST), "end_date": pd.NaT})
    current_set = {r["ticker"] for r in rows}

    last_add: dict[str, pd.Timestamp] = {}
    for _, r in ch.iterrows():
        if isinstance(r["added"], str) and r["added"].strip():
            last_add[_norm(r["added"])] = r["date"]
        if isinstance(r["removed"], str) and r["removed"].strip():
            t = _norm(r["removed"])
            if t in current_set and last_add.get(t, pd.Timestamp.min) > r["date"]:
                continue
            rows.append(
                {"ticker": t, "start_date": last_add.pop(t, pd.Timestamp(EARLIEST)), "end_date": r["date"] - pd.Timedelta(days=1)}
            )
    out = pd.DataFrame(rows)
    out["sector"] = out["ticker"].map(sector).fillna("")
    out = out[out["end_date"].isna() | (out["end_date"] >= out["start_date"])]
    return out.drop_duplicates(["ticker", "start_date"]).sort_values(["ticker", "start_date"]).reset_index(drop=True)


def fetch_sp500_membership(timeout: int = 30) -> pd.DataFrame:
    import requests

    html = requests.get(WIKI_URL, timeout=timeout, headers={"User-Agent": "Mozilla/5.0 thrive-alpha"}).text
    tables = pd.read_html(StringIO(html))
    current = next(t for t in tables if any(str(c).lower().startswith("symbol") for c in _flatten(t.copy()).columns))
    changes = next((t for t in tables if _is_changes_table(t)), None)
    if changes is None:
        import logging

        logging.getLogger(__name__).warning(
            "S&P 500 change log not found on %s — membership has current names only (survivorship bias)", WIKI_URL
        )
    return membership_from_tables(current, changes)


def fetch_sp500_membership_with_history(timeout: int = 30) -> pd.DataFrame:
    """Historical ranges (incl. removed names) from HISTORY_URL + GICS sectors from Wikipedia."""
    import requests

    hist = pd.read_csv(StringIO(requests.get(HISTORY_URL, timeout=timeout).text))
    hist["ticker"] = hist["ticker"].map(_norm)
    hist["start_date"] = pd.to_datetime(hist["start_date"], errors="coerce")
    hist["end_date"] = pd.to_datetime(hist["end_date"], errors="coerce")
    try:
        sectors = sector_map(fetch_sp500_membership(timeout))
    except Exception:
        sectors = {}
    hist["sector"] = hist["ticker"].map(sectors).fillna("")
    return hist.dropna(subset=["start_date"]).sort_values(["ticker", "start_date"]).reset_index(drop=True)


def save_membership(df: pd.DataFrame, path: str | Path | None = None) -> Path:
    p = Path(path or DEFAULT_MEMBERSHIP_CSV)
    p.parent.mkdir(parents=True, exist_ok=True)
    d = df.copy()
    for c in ("start_date", "end_date"):
        d[c] = pd.to_datetime(d[c]).dt.strftime("%Y-%m-%d")
    d.to_csv(p, index=False)
    return p


def load_membership(path: str | Path | None = None) -> pd.DataFrame:
    d = pd.read_csv(Path(path or DEFAULT_MEMBERSHIP_CSV), dtype={"sector": str}, keep_default_na=False)
    d["start_date"] = pd.to_datetime(d["start_date"])
    d["end_date"] = pd.to_datetime(d["end_date"].replace("", None))
    return d


def members_on(membership: pd.DataFrame, as_of) -> list[str]:
    ts = pd.Timestamp(as_of)
    m = membership[(membership["start_date"] <= ts) & (membership["end_date"].isna() | (membership["end_date"] >= ts))]
    return sorted(m["ticker"].unique())


def membership_mask(panel: pd.DataFrame, membership: pd.DataFrame) -> pd.Series:
    """Boolean Series over a (date, ticker) panel: was the ticker an index member that day."""
    idx = panel.index.to_frame(index=False)
    merged = idx.merge(membership[["ticker", "start_date", "end_date"]], on="ticker", how="left")
    ok = (merged["date"] >= merged["start_date"]) & (merged["end_date"].isna() | (merged["date"] <= merged["end_date"]))
    ok = ok & merged["start_date"].notna()
    keep = ok.groupby([merged["date"], merged["ticker"]]).any()
    return keep.reindex(pd.MultiIndex.from_frame(idx)).fillna(False).set_axis(panel.index)


def sector_map(membership: pd.DataFrame) -> dict[str, str]:
    m = membership[membership["sector"].astype(str) != ""]
    return dict(zip(m["ticker"], m["sector"]))
