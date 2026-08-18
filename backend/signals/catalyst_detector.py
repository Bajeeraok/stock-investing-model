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


FRIENDLY_LABELS = {
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

BULLISH_EVENTS = {
    "M&A", "MAJOR_DEAL", "PARTNERSHIP", "FDA_APPROVAL",
    "EARNINGS_BLOWOUT", "EARNINGS_BEAT", "GUIDANCE_RAISE",
    "ANALYST_UPGRADE", "CAPITAL_RETURN", "IPO_SPINOFF", "PT_RAISE",
}
BEARISH_EVENTS = {
    "REGULATORY_ACTION", "EARNINGS_MISS", "GUIDANCE_CUT",
    "ANALYST_DOWNGRADE", "LEGAL_RISK", "PT_CUT",
}
_WATCH_HINTS = {
    "M&A": "deal terms / close risk",
    "MAJOR_DEAL": "contract follow-through",
    "PARTNERSHIP": "named partner confirmation",
    "FDA_APPROVAL": "label / commercial timing",
    "REGULATORY_ACTION": "probe headlines vs price hold",
    "EARNINGS_BLOWOUT": "gap hold vs fade next session",
    "EARNINGS_BEAT": "gap hold vs fade next session",
    "EARNINGS_MISS": "stabilization after the print",
    "GUIDANCE_RAISE": "estimate revisions catch up",
    "GUIDANCE_CUT": "estimate revisions catch down",
    "ANALYST_UPGRADE": "follow-through vs one-day pop",
    "ANALYST_DOWNGRADE": "follow-through vs one-day dump",
    "PT_RAISE": "street cluster vs your band",
    "PT_CUT": "street cluster vs your stop",
    "CEO_CHANGE": "succession / strategy note",
    "RESTRUCTURING": "charge size vs core thesis",
    "CAPITAL_RETURN": "buyback pace vs dilution",
    "LEGAL_RISK": "case status vs thesis break",
    "IPO_SPINOFF": "when-issued / listing date",
}


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
        from signals.time_et import now_et, parse_iso_to_et

        if now is None:
            now = now_et()
        pub = parse_iso_to_et(published_at)
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

    friendly = FRIENDLY_LABELS.get(top.event_type, top.event_type.lower().replace("_", " "))
    age_label = f"{top.age_hours:.0f}h ago" if top.age_hours < 24 else f"{top.age_hours / 24:.0f}d ago"

    if top.event_type in BULLISH_EVENTS:
        override = (
            f"Catalyst active ({friendly}, {age_label}) \u2014 "
            "momentum regime may dominate standard valuation model. "
            "Price action near the event is news-driven, not pattern-driven."
        )
    elif top.event_type in BEARISH_EVENTS:
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


def _direction_for(event_type: str) -> str:
    if event_type in BULLISH_EVENTS:
        return "unlocks"
    if event_type in BEARISH_EVENTS:
        return "breaks"
    return "watch"


def _horizon_from_age(hours: float) -> str:
    if hours < 24:
        return "days"
    if hours < 168:
        return "1-2 weeks"
    return "4-12 weeks"


def _age_label(hours: float) -> str:
    if hours >= 900:
        return ""
    if hours < 24:
        return f"{hours:.0f}h ago"
    return f"{hours / 24:.0f}d ago"


def build_catalyst_note_cards(
    headlines: list[dict[str, Any]] | None,
    *,
    ticker: str = "",
    max_cards: int = 4,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Cluster classified headlines into 2–4 advisory cards for the news rail.

    Advisory only — never mutates bands, gates, or scores. Draft notes are
    meant for the user to confirm into the decision journal.
    """
    if not headlines:
        return []

    clusters: dict[str, dict[str, Any]] = {}
    for item in headlines:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or item.get("headline") or "").strip()
        if not title:
            continue
        body = str(item.get("text") or item.get("description") or item.get("summary") or "")
        pub = item.get("published") or item.get("publishedDate") or item.get("published_at") or item.get("date")
        url = str(item.get("url") or item.get("link") or "")
        age = _article_age_hours(str(pub) if pub else None, now)
        hits = _classify_headline(title, body)
        if not hits:
            continue
        event_type, impact = max(hits, key=lambda h: h[1])
        row = clusters.get(event_type)
        if row is None or impact > row["impact"] or (impact == row["impact"] and age < row["age_hours"]):
            clusters[event_type] = {
                "event_type": event_type,
                "impact": impact,
                "title": title[:180],
                "url": url or None,
                "source": _extract_domain(url),
                "age_hours": round(age, 1),
                "headline_count": (row["headline_count"] + 1) if row else 1,
            }
        else:
            row["headline_count"] = int(row["headline_count"]) + 1

    ranked = sorted(clusters.values(), key=lambda r: (-int(r["impact"]), float(r["age_hours"])))
    cards: list[dict[str, Any]] = []
    sym = (ticker or "").strip().upper()
    for row in ranked[: max(1, min(4, max_cards))]:
        et = str(row["event_type"])
        friendly = FRIENDLY_LABELS.get(et, et.lower().replace("_", " "))
        direction = _direction_for(et)
        age_h = float(row["age_hours"])
        age_l = _age_label(age_h)
        source = row["source"] if row["source"] != "unknown" else ""
        draft_bits = [f"{sym} · {friendly} ({direction}) — {row['title']}"]
        meta = " · ".join(x for x in (source, age_l) if x)
        if meta:
            draft_bits.append(meta)
        draft_bits.append("Advisory only — does not change bands or gates.")
        cards.append({
            "name": friendly,
            "event_type": et,
            "direction": direction,
            "mechanism": row["title"],
            "watch": _WATCH_HINTS.get(et, "price reaction vs your plan"),
            "horizon": _horizon_from_age(age_h),
            "source": source or None,
            "age_hours": None if age_h >= 900 else age_h,
            "age_label": age_l or None,
            "url": row["url"],
            "headline_count": int(row["headline_count"]),
            "draft_note": " ".join(draft_bits)[:500],
        })
    return cards

