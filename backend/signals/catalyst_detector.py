"""
Catalyst detection layer for news headlines.

Classifies FMP/AV/Yahoo headlines into high-impact event categories
(M&A, FDA, earnings surprise, major partnership, restructuring, legal)
and flags "catalyst active" when a significant event is detected
within the last 48 hours.

Does NOT modify existing signal scores — produces an advisory payload
that downstream consumers (ticker_detail, confidence_engine) can use.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any


# ── Event type patterns ─────────────────────────────────────────────────
# Each tuple: (compiled regex on lowercased title+body, event_type, impact 1-3)

_EVENT_PATTERNS: list[tuple[re.Pattern, str, int]] = [
    # M&A / Deals (impact 3)
    (re.compile(r"(acquir|acquisition|merger|buyout|takeover|buy.{0,10}(company|unit|division)|agreed to (buy|acquire)|deal (worth|valued))"), "M&A", 3),
    (re.compile(r"(preliminary agreement|manufacturing (deal|agreement|partnership)|foundry (deal|agreement|contract))"), "M&A", 3),

    # Major partnership / contract (impact 2-3)
    (re.compile(r"(major (contract|deal|partnership)|multi.?billion|landmark (deal|agreement|partnership))"), "MAJOR_DEAL", 3),
    (re.compile(r"(strategic (partnership|alliance|agreement)|signs? (deal|contract|agreement) with)"), "PARTNERSHIP", 2),

    # FDA / regulatory approval (impact 3)
    (re.compile(r"(fda (approv|clear|grant|accept)|eua|breakthrough therapy|priority review|regulatory (approv|clear))"), "FDA_APPROVAL", 3),
    (re.compile(r"(antitrust|doj|ftc|eu commission|regulatory (action|probe|investigat|fine|block))"), "REGULATORY_ACTION", 3),

    # Earnings surprise (impact 2-3)
    (re.compile(r"(earnings|revenue|profit|eps).{0,25}(crush|smash|blow.?past|massive.?beat|blowout)"), "EARNINGS_BLOWOUT", 3),
    (re.compile(r"(earnings|revenue|profit|eps).{0,25}(beat|surpass|exceed|top)"), "EARNINGS_BEAT", 2),
    (re.compile(r"(earnings|revenue|profit|eps).{0,25}(miss|disappoint|fall short|below)"), "EARNINGS_MISS", 2),
    (re.compile(r"(guidance|outlook).{0,20}(raised|hiked|boosted|above|raised above)"), "GUIDANCE_RAISE", 2),
    (re.compile(r"(guidance|outlook).{0,20}(lowered|cut|slashed|below|withdrew|pulled)"), "GUIDANCE_CUT", 2),

    # Analyst upgrades/downgrades (impact 1-2)
    (re.compile(r"(upgrade[ds]? (to )?(buy|strong buy|outperform|overweight)|upgrade[ds]? .{0,20}(buy|outperform))"), "ANALYST_UPGRADE", 2),
    (re.compile(r"(downgrade[ds]? (to )?(sell|underperform|underweight|reduce)|downgrade[ds]? .{0,20}(sell|underperform))"), "ANALYST_DOWNGRADE", 2),
    (re.compile(r"price target (raised|hiked|increased|boosted) to"), "PT_RAISE", 1),
    (re.compile(r"price target (lowered|cut|reduced|slashed) to"), "PT_CUT", 1),

    # Management / restructuring (impact 2)
    (re.compile(r"(ceo (resig|fired|ousted|replaced|steps down|depart)|new ceo|ceo (appoint|named|hired))"), "CEO_CHANGE", 2),
    (re.compile(r"(massive layoff|restructur|workforce reduction|job cut.{0,15}\d{3,})"), "RESTRUCTURING", 2),

    # Share buyback / dividend (impact 1)
    (re.compile(r"(\$\d+\s*billion.{0,20}buyback|massive (buyback|repurchase)|special dividend)"), "CAPITAL_RETURN", 2),

    # Legal / fraud (impact 2-3)
    (re.compile(r"(fraud|sec (charges|sues|investigat)|criminal|indictment|class.?action)"), "LEGAL_RISK", 3),

    # IPO / spin-off (impact 2)
    (re.compile(r"(ipo|spin.?off|goes public|direct listing)"), "IPO_SPINOFF", 2),
]


@dataclass
class CatalystEvent:
    """A single detected catalyst from a headline."""
    event_type: str
    impact: int          # 1-3 scale
    headline: str
    published_at: str | None
    age_hours: float     # hours since publication
    source_domain: str


@dataclass
class CatalystPayload:
    """Result of catalyst detection for a ticker."""
    active: bool = False
    events: list[CatalystEvent] = field(default_factory=list)
    top_event_type: str | None = None
    top_impact: int = 0
    headline_summary: str | None = None
    override_note: str | None = None
    hours_since_catalyst: float | None = None


def _extract_domain(url: str | None) -> str:
    if not url:
        return "unknown"
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url if url.startswith("http") else f"https://{url}")
        domain = parsed.netloc or ""
        return re.sub(r"^www\.", "", domain.lower())
    except Exception:
        return "unknown"


def _article_age_hours(published_at: str | None, now: datetime | None = None) -> float:
    if not published_at:
        return 999.0
    try:
        if now is None:
            now = datetime.now(timezone.utc)
        pub = datetime.fromisoformat(str(published_at).replace("Z", "+00:00"))
        return max(0.0, (now - pub).total_seconds() / 3600)
    except (ValueError, TypeError, OSError):
        return 999.0


def _classify_headline(title: str, body: str = "") -> list[tuple[str, int]]:
    """Return list of (event_type, impact) matches for a headline."""
    combined = f"{title} {body}".lower()
    hits: list[tuple[str, int]] = []
    seen_types: set[str] = set()
    for pattern, event_type, impact in _EVENT_PATTERNS:
        if event_type in seen_types:
            continue
        if pattern.search(combined):
            hits.append((event_type, impact))
            seen_types.add(event_type)
    return hits


def detect_catalysts(
    articles: list[dict[str, Any]],
    ticker: str,
    *,
    max_age_hours: float = 48.0,
    min_impact: int = 2,
    now: datetime | None = None,
) -> CatalystPayload:
    """
    Scan recent news articles for high-impact catalysts.

    Only flags events within `max_age_hours` (default 48h) and
    with impact >= `min_impact` (default 2, i.e. skip PT changes).

    Returns a CatalystPayload that is purely advisory — does not
    modify any existing scores or signals.
    """
    if not articles:
        return CatalystPayload()

    events: list[CatalystEvent] = []

    for item in articles:
        if not isinstance(item, dict):
            continue
        title = (item.get("title") or item.get("headline") or "")[:300]
        body = (
            item.get("text") or item.get("description")
            or item.get("content") or item.get("summary") or ""
        )[:1000]
        pub = item.get("publishedDate") or item.get("published_at") or item.get("date")
        url = item.get("url") or item.get("link") or item.get("sourceUrl") or ""

        age = _article_age_hours(str(pub) if pub else None, now)
        if age > max_age_hours:
            continue

        hits = _classify_headline(title, body)
        for event_type, impact in hits:
            if impact >= min_impact:
                events.append(CatalystEvent(
                    event_type=event_type,
                    impact=impact,
                    headline=title[:120],
                    published_at=str(pub) if pub else None,
                    age_hours=round(age, 1),
                    source_domain=_extract_domain(str(url)),
                ))

    if not events:
        return CatalystPayload()

    events.sort(key=lambda e: (-e.impact, e.age_hours))
    top = events[0]

    _FRIENDLY_LABELS = {
        "M&A": "M&A / acquisition",
        "MAJOR_DEAL": "major deal",
        "PARTNERSHIP": "strategic partnership",
        "FDA_APPROVAL": "FDA / regulatory approval",
        "REGULATORY_ACTION": "regulatory action",
        "EARNINGS_BLOWOUT": "earnings blowout",
        "EARNINGS_BEAT": "earnings beat",
        "EARNINGS_MISS": "earnings miss",
        "GUIDANCE_RAISE": "guidance raise",
        "GUIDANCE_CUT": "guidance cut",
        "ANALYST_UPGRADE": "analyst upgrade",
        "ANALYST_DOWNGRADE": "analyst downgrade",
        "PT_RAISE": "price target raise",
        "PT_CUT": "price target cut",
        "CEO_CHANGE": "CEO change",
        "RESTRUCTURING": "restructuring",
        "CAPITAL_RETURN": "capital return (buyback/dividend)",
        "LEGAL_RISK": "legal / fraud risk",
        "IPO_SPINOFF": "IPO / spin-off",
    }

    friendly = _FRIENDLY_LABELS.get(top.event_type, top.event_type.lower().replace("_", " "))
    age_label = f"{top.age_hours:.0f}h ago" if top.age_hours < 24 else f"{top.age_hours / 24:.0f}d ago"

    bullish_events = {"M&A", "MAJOR_DEAL", "PARTNERSHIP", "FDA_APPROVAL",
                      "EARNINGS_BLOWOUT", "EARNINGS_BEAT", "GUIDANCE_RAISE",
                      "ANALYST_UPGRADE", "CAPITAL_RETURN", "IPO_SPINOFF"}
    bearish_events = {"REGULATORY_ACTION", "EARNINGS_MISS", "GUIDANCE_CUT",
                      "ANALYST_DOWNGRADE", "LEGAL_RISK"}

    if top.event_type in bullish_events:
        override = (
            f"Catalyst active ({friendly}, {age_label}) \u2014 "
            "momentum regime may dominate standard valuation model. "
            "Price action near the event is news-driven, not pattern-driven."
        )
    elif top.event_type in bearish_events:
        override = (
            f"Catalyst active ({friendly}, {age_label}) \u2014 "
            "negative event may override bullish technicals. "
            "Wait for price to stabilize before trusting pattern signals."
        )
    else:
        override = (
            f"Catalyst active ({friendly}, {age_label}) \u2014 "
            "significant event detected; standard model may lag until digested."
        )

    return CatalystPayload(
        active=True,
        events=events,
        top_event_type=top.event_type,
        top_impact=top.impact,
        headline_summary=top.headline,
        override_note=override,
        hours_since_catalyst=top.age_hours,
    )
