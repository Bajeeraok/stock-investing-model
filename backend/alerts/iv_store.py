from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path


@dataclass(frozen=True)
class IVSnapshot:
    symbol: str
    as_of: date
    atm_iv: float  # annualized (0-1)


class IVHistoryFileStore:
    """
    Persist IV snapshots per symbol as CSV in data/alerts/iv_history/{SYMBOL}.csv.

    This lets IV Rank become "real" over time (vs proxy RV anchoring).
    """

    def __init__(self, root: Path):
        self.root = root
        self.dir = root / "iv_history"
        self.dir.mkdir(parents=True, exist_ok=True)

    def _path(self, symbol: str) -> Path:
        return self.dir / f"{symbol.upper()}.csv"

    def append(self, snap: IVSnapshot) -> None:
        p = self._path(snap.symbol)
        exists = p.exists()
        with p.open("a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if not exists:
                w.writerow(["date", "atm_iv"])
            w.writerow([snap.as_of.isoformat(), f"{snap.atm_iv:.6f}"])

    def load_series(self, symbol: str) -> list[tuple[date, float]]:
        p = self._path(symbol)
        if not p.exists():
            return []
        out: list[tuple[date, float]] = []
        with p.open("r", newline="", encoding="utf-8") as f:
            r = csv.DictReader(f)
            for row in r:
                try:
                    d = date.fromisoformat(str(row["date"]))
                    iv = float(row["atm_iv"])
                    out.append((d, iv))
                except Exception:
                    continue
        out.sort(key=lambda x: x[0])
        return out

