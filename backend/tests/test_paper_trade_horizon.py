"""Paper trade outcome horizon uses business-day target, not raw index offset."""

from __future__ import annotations

import pandas as pd
from pandas.tseries.offsets import BDay


def test_first_snapshot_on_or_after_bday():
    dates = [
        "2024-01-02",
        "2024-01-03",
        "2024-01-04",
        "2024-01-05",
        "2024-01-08",
        "2024-01-09",
        "2024-01-10",
        "2024-01-11",
        "2024-01-12",
        "2024-01-16",
        "2024-01-17",
        "2024-01-18",
        "2024-01-19",
        "2024-01-22",
        "2024-01-23",
        "2024-01-24",
        "2024-01-25",
        "2024-01-26",
        "2024-01-29",
        "2024-01-30",
        "2024-01-31",
        "2024-02-01",
        "2024-02-02",
        "2024-02-05",
        "2024-02-06",
    ]
    as_of = "2024-01-02"
    horizon = 20
    target_ts = pd.Timestamp(as_of).normalize() + BDay(horizon)
    next_date = None
    for d in dates:
        if pd.Timestamp(d).normalize() >= target_ts:
            next_date = d
            break
    assert next_date == "2024-01-30"
