"""
Point-in-time feature store.

Each daily run appends rows stamped with ``as_of`` (the market date the values describe)
and ``knowledge_time`` (when we computed them). ``as_of_view(date)`` returns, per ticker,
the latest values that were *known* by that date, so backtests can replay exactly what
the live system saw instead of restated or revised data.
"""
from __future__ import annotations

import time
from pathlib import Path

import pandas as pd

BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_STORE = BACKEND_ROOT / "data" / "alpha" / "pit_store"


class PITStore:
    def __init__(self, root: str | Path | None = None):
        self.root = Path(root or DEFAULT_STORE)

    def _path(self, name: str, as_of: str) -> Path:
        return self.root / name / f"{as_of}.csv.gz"

    def append(self, name: str, df: pd.DataFrame, as_of, knowledge_time: str | None = None) -> Path:
        """``df`` indexed by ticker. Writes a new vintage file; never overwrites prior vintages."""
        as_of = str(pd.Timestamp(as_of).date())
        kt = knowledge_time or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        d = df.copy()
        d.index.name = "ticker"
        d = d.reset_index()
        d["as_of"] = as_of
        d["knowledge_time"] = kt
        p = self._path(name, as_of)
        p.parent.mkdir(parents=True, exist_ok=True)
        if p.exists():
            d = pd.concat([pd.read_csv(p), d], ignore_index=True)
        d.to_csv(p, index=False)
        return p

    def load(self, name: str) -> pd.DataFrame:
        files = sorted((self.root / name).glob("*.csv.gz"))
        if not files:
            return pd.DataFrame()
        return pd.concat([pd.read_csv(f) for f in files], ignore_index=True)

    def as_of_view(self, name: str, date) -> pd.DataFrame:
        """Latest known row per ticker with as_of <= date and knowledge_time <= end of date."""
        d = self.load(name)
        if d.empty:
            return d
        ts = pd.Timestamp(date)
        cutoff = (ts + pd.Timedelta(days=1)).strftime("%Y-%m-%dT00:00:00Z")
        d = d[(pd.to_datetime(d["as_of"]) <= ts) & (d["knowledge_time"] < cutoff)]
        d = d.sort_values(["as_of", "knowledge_time"])
        return d.groupby("ticker").tail(1).set_index("ticker")
