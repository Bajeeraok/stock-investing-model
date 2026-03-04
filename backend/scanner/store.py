from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path


class ScannerStore:
    """
    File-backed store for scanner alerts.
    Keeps the scanner resilient across app restarts (important on Railway).
    """

    def __init__(self, data_root: Path):
        self.dir = data_root / "scanner"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.alerts_path = self.dir / "alerts.jsonl"
        self.dismissed_path = self.dir / "dismissed.json"
        self.stats_path = self.dir / "stats.json"

    def append_alert(self, alert) -> None:
        with self.alerts_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(alert), ensure_ascii=False) + "\n")

    def load_alerts(self, limit: int = 200) -> list[dict]:
        if not self.alerts_path.exists():
            return []
        lines = self.alerts_path.read_text(encoding="utf-8").splitlines()
        tail = lines[-limit:] if limit > 0 else lines
        out: list[dict] = []
        for ln in reversed(tail):
            try:
                out.append(json.loads(ln))
            except Exception:
                continue
        return out

    def load_dismissed(self) -> set[str]:
        if not self.dismissed_path.exists():
            return set()
        try:
            j = json.loads(self.dismissed_path.read_text(encoding="utf-8"))
            if isinstance(j, list):
                return set(str(x) for x in j)
            if isinstance(j, dict) and "ids" in j and isinstance(j["ids"], list):
                return set(str(x) for x in j["ids"])
        except Exception:
            return set()
        return set()

    def save_dismissed(self, ids: set[str]) -> None:
        self.dismissed_path.write_text(json.dumps({"ids": sorted(ids)}, indent=2), encoding="utf-8")

    def write_stats(self, stats: dict) -> None:
        self.stats_path.write_text(json.dumps(stats, indent=2), encoding="utf-8")

    def read_stats(self) -> dict:
        if not self.stats_path.exists():
            return {}
        try:
            return json.loads(self.stats_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

