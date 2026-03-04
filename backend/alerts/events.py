from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class AlertEvent:
    id: str
    ts: str
    ticker: str
    alert_type: str
    severity: str
    title: str
    message: str
    payload: dict
    dedupe_key: str

    @classmethod
    def create(
        cls,
        *,
        ticker: str,
        alert_type: str,
        severity: str,
        title: str,
        message: str,
        payload: dict | None = None,
        dedupe_key: str | None = None,
    ) -> "AlertEvent":
        ts = datetime.now(tz=timezone.utc).isoformat()
        return cls(
            id=str(uuid.uuid4()),
            ts=ts,
            ticker=ticker.upper(),
            alert_type=alert_type,
            severity=severity,
            title=title,
            message=message,
            payload=payload or {},
            dedupe_key=dedupe_key or f"{ticker.upper()}:{alert_type}",
        )


class AlertEventStore:
    def __init__(self, data_root: Path):
        self.dir = data_root / "alerts"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.events_path = self.dir / "events.jsonl"
        self.status_path = self.dir / "status.json"
        self.latest_path = self.dir / "latest.json"

    def append_events(self, events: list[AlertEvent]) -> None:
        if not events:
            return
        with self.events_path.open("a", encoding="utf-8") as f:
            for ev in events:
                f.write(json.dumps(asdict(ev), ensure_ascii=False) + "\n")

    def write_status(self, status: dict) -> None:
        self.status_path.write_text(json.dumps(status, indent=2), encoding="utf-8")

    def write_latest(self, latest: dict) -> None:
        self.latest_path.write_text(json.dumps(latest, indent=2), encoding="utf-8")

    def read_events(self, limit: int = 200) -> list[dict]:
        if not self.events_path.exists():
            return []
        # Read from end-ish; jsonl is append-only.
        lines = self.events_path.read_text(encoding="utf-8").splitlines()
        tail = lines[-limit:] if limit > 0 else lines
        out: list[dict] = []
        for ln in reversed(tail):
            try:
                out.append(json.loads(ln))
            except Exception:
                continue
        return out

    def read_status(self) -> dict:
        if not self.status_path.exists():
            return {}
        try:
            return json.loads(self.status_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def read_latest(self) -> dict:
        if not self.latest_path.exists():
            return {}
        try:
            return json.loads(self.latest_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

