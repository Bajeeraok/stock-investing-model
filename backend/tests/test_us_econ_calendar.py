from datetime import date

from signals.us_econ_calendar import classify, fomc_events, from_fmp

RAW = [
    {"date": "2026-11-13 00:00:00", "country": "IR", "event": "Martyrdom of Fatima"},
    {"date": "2026-11-13 13:30:00", "country": "US", "event": "Producer Price Index MoM (Oct)", "estimate": 0.4, "actual": 0.6, "previous": 1.3},
    {"date": "2026-11-10 13:30:00", "country": "US", "event": "Inflation Rate YoY (Oct)", "estimate": 3.9, "actual": None},
    {"date": "2026-11-23 14:45:00", "country": "US", "event": "S&P Global Services PMI (Nov)"},
]


def test_us_only_with_surprise_and_et_time():
    ev = from_fmp(RAW)
    assert [e["event"] for e in ev] == ["Inflation Rate YoY (Oct)", "Producer Price Index MoM (Oct)"]
    ppi = ev[1]
    assert ppi["time_et"] == "8:30 AM" and ppi["date"].startswith("2026-11-13T08:30") and ppi["surprise"] == 0.2
    assert ev[0]["tier"] == 1 and ev[0]["surprise"] is None


def test_classify_and_fomc():
    assert classify("Non Farm Payrolls (Nov)")[0] == 1
    assert classify("Thomson Reuters IPSOS PCSI") is None
    f = fomc_events(date(2026, 12, 1), date(2026, 12, 31))
    assert len(f) == 1 and f[0]["date"].startswith("2026-12-09T14:00")
