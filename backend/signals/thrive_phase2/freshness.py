"""Signal freshness by investor profile."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from ._constants import SIGNAL_MAX_AGE
from .models import SetupSignal


class SignalFreshnessChecker:
    def is_fresh(self, signal_time: datetime, profile: str) -> bool:
        max_age = SIGNAL_MAX_AGE.get(profile, timedelta(days=1))
        return (datetime.now() - signal_time) <= max_age

    def time_remaining(self, signal_time: datetime, profile: str) -> Optional[timedelta]:
        max_age = SIGNAL_MAX_AGE.get(profile, timedelta(days=1))
        age = datetime.now() - signal_time
        remaining = max_age - age
        return remaining if remaining.total_seconds() > 0 else None

    def check_signal(self, signal: SetupSignal) -> dict:
        fresh = self.is_fresh(signal.generated_at, signal.profile)
        remaining = self.time_remaining(signal.generated_at, signal.profile)
        return {
            "is_fresh": fresh,
            "generated_at": signal.generated_at.strftime("%Y-%m-%d %H:%M"),
            "time_remaining": str(remaining).split(".")[0] if remaining else "EXPIRED",
            "action": "USE" if fresh else "REFRESH — signal expired",
        }
