"""
US economic calendar: FMP US releases (with estimate/actual/surprise) + FOMC decision days + Treasury coupon
auctions (TreasuryDirect, free). Display and event-risk context only; no signal reads it.
"""

from __future__ import annotations

import json
import logging
import urllib.request
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")

# Fed's published 2026 schedule (decision = second day, 2:00 PM ET).
FOMC_DECISIONS = (
    "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17", "2026-07-29", "2026-09-16", "2026-10-28", "2026-12-09",
)

# (keywords, tier, risk groups). First match wins; tier 1 = market-moving.
_RULES: tuple[tuple[tuple[str, ...], int, str], ...] = (
    (("fomc minutes",), 2, "Rates"),
    (("interest rate decision", "fomc", "fed chair", "powell"), 1, "Everything; rates, banks, growth"),
    (("cpi", "inflation rate"), 1, "Rates, growth/tech, REITs"),
    (("pce price",), 1, "Rates, growth/tech"),
    (("non farm", "nonfarm", "non-farm", "unemployment rate"), 1, "Rates, cyclicals"),
    (("gdp growth", "gdp price", "gdp "), 1, "Cyclicals, small caps"),
    (("producer price", "ppi"), 2, "Rates, margins"),
    (("retail sales",), 2, "Consumer discretionary"),
    (("ism manufacturing", "ism services", "ism non"), 2, "Industrials, materials"),
    (("jolts", "initial jobless claims", "adp employment"), 2, "Rates, cyclicals"),
    (("michigan consumer sentiment", "consumer confidence"), 3, "Consumer discretionary"),
    (("fed ",), 3, "Rates"),
    (("housing starts", "new home sales", "existing home sales", "building permits"), 3, "Homebuilders, REITs"),
    (("durable goods", "industrial production"), 3, "Industrials"),
)


PER_FAMILY_PER_DAY = 2


def _family(name: str) -> int | None:
    n = name.lower() + " "
    for i, (keys, _, _) in enumerate(_RULES):
        if any(k in n for k in keys):
            return i
    return None


def classify(name: str) -> tuple[int, str] | None:
    i = _family(name)
    return (_RULES[i][1], _RULES[i][2]) if i is not None else None


def _to_et(raw: str) -> datetime | None:
    try:
        d = datetime.fromisoformat(str(raw).replace(" ", "T")[:19])
    except ValueError:
        return None
    return d.replace(tzinfo=timezone.utc).astimezone(ET)


def _num(v: Any) -> float | None:
    try:
        return float(v) if v is not None and v != "" else None
    except (TypeError, ValueError):
        return None


def from_fmp(raw: list[dict], max_tier: int = 2) -> list[dict[str, Any]]:
    out = []
    for e in raw or []:
        if not isinstance(e, dict) or (e.get("country") or "").upper() != "US":
            continue
        name = str(e.get("event") or "").strip()
        c = classify(name)
        if not c or c[0] > max_tier:
            continue
        d = _to_et(e.get("date") or "")
        if d is None:
            continue
        est, act = _num(e.get("estimate")), _num(e.get("actual"))
        out.append({
            "date": d.isoformat(),
            "time_et": d.strftime("%-I:%M %p"),
            "event": name,
            "name": name,
            "country": "US",
            "tier": c[0],
            "groups": c[1],
            "estimate": est,
            "actual": act,
            "previous": _num(e.get("previous")),
            "surprise": round(act - est, 3) if act is not None and est is not None else None,
            "unit": e.get("unit"),
            "source": "FMP",
            "_family": _family(name),
        })
    # One release (e.g. PPI) comes as 5–7 variants; keep the 2 per day that have a forecast, note the rest.
    out.sort(key=lambda e: (e["date"][:10], e["_family"], e["estimate"] is None and e["actual"] is None, len(e["event"])))
    kept: list[dict[str, Any]] = []
    for e in out:
        same = [k for k in kept if k["date"][:10] == e["date"][:10] and k["_family"] == e["_family"]]
        if len(same) < PER_FAMILY_PER_DAY:
            kept.append(e)
        else:
            same[-1]["more"] = same[-1].get("more", 0) + 1
    for e in kept:
        e.pop("_family", None)
    return kept


def fomc_events(start: date, end: date) -> list[dict[str, Any]]:
    out = []
    for ds in FOMC_DECISIONS:
        d = date.fromisoformat(ds)
        if start <= d <= end:
            dt = datetime(d.year, d.month, d.day, 14, 0, tzinfo=ET)
            out.append({"date": dt.isoformat(), "time_et": "2:00 PM", "event": "FOMC rate decision", "name": "FOMC rate decision",
                        "country": "US", "tier": 1, "groups": "Everything; rates, banks, growth", "source": "Federal Reserve"})
    return out


def treasury_auctions(start: date, end: date) -> list[dict[str, Any]]:
    try:
        req = urllib.request.Request(
            "https://www.treasurydirect.gov/TA_WS/securities/upcoming?format=json", headers={"User-Agent": "ThriveAlpha/1.0"}
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
    except Exception as e:
        logger.debug("treasury auctions: %s", e)
        return []
    out = []
    for a in data if isinstance(data, list) else []:
        typ = a.get("securityType") or ""
        if typ not in ("Note", "Bond", "TIPS", "FRN") and not (typ == "Bill" and "52" in (a.get("securityTerm") or "")):
            continue
        ds = (a.get("auctionDate") or a.get("competitiveAuctionCloseDate") or "")[:10]
        try:
            d = date.fromisoformat(ds)
        except ValueError:
            continue
        if not start <= d <= end:
            continue
        amt = _num(a.get("offeringAmount"))
        name = f"{a.get('securityTerm')} {typ} auction" + (f" (${amt / 1e9:.0f}B)" if amt else "")
        dt = datetime(d.year, d.month, d.day, 13, 0, tzinfo=ET)
        out.append({"date": dt.isoformat(), "time_et": "1:00 PM", "event": name, "name": name, "country": "US",
                    "tier": 2 if typ in ("Note", "Bond") else 3, "groups": "Rates, long-duration stocks", "source": "TreasuryDirect"})
    return out


def build_us_calendar(config: dict, days: int = 7) -> list[dict[str, Any]]:
    from signals.fmp_client import BASE, _request, get_api_key

    today = date.today()
    end = today + timedelta(days=days)
    events: list[dict[str, Any]] = []
    key = get_api_key(config)
    if key:
        data, err = _request(f"{BASE}/economic-calendar?from={today - timedelta(days=1)}&to={end}", key)
        if not err and isinstance(data, list):
            events += from_fmp(data)
    if not any("rate decision" in e["event"].lower() for e in events):
        events += fomc_events(today, end)
    events += treasury_auctions(today, end)
    lo = (today - timedelta(days=1)).isoformat()
    events = [e for e in events if e["date"][:10] >= lo]
    events.sort(key=lambda e: (e["date"], e["tier"]))
    return events[:60]
