"""
Catalyst Translation Matrix — map raw feeds into 6 retail categories and pick
the single biggest driver for 10-second trading notes.

Categories:
  MACRO_RATES   — CPI, PCE, Fed/Powell, rate hikes
  GEOPOLITICAL  — war, sanctions, election, tariffs
  CROSS_ASSET   — oil, US10Y, DXY
  BINARY_EVENT  — earnings, FDA, product launch
  SMART_MONEY   — insider selling, analyst downgrade, short interest
  TECHNICAL     — RSI/HMM/overbought/breakdown/breakout
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Iterable

# Higher = more important when competing for PRIMARY_DRIVER.
CATEGORY_PRIORITY: dict[str, int] = {
    "BINARY_EVENT": 100,
    "SMART_MONEY": 85,
    "MACRO_RATES": 75,
    "GEOPOLITICAL": 70,
    "CROSS_ASSET": 55,
    "TECHNICAL": 30,
}

PLAIN_ENGLISH: dict[str, str] = {
    "MACRO_RATES": "Inflation & interest rates",
    "GEOPOLITICAL": "Political & global news",
    "CROSS_ASSET": "Market-wide pressure",
    "BINARY_EVENT": "Big company news / event",
    "SMART_MONEY": "Big institutional traders",
    "TECHNICAL": "Chart / momentum setup",
}

# (category, keywords) — first match wins within a scan; order = specificity.
_KEYWORD_RULES: list[tuple[str, tuple[str, ...]]] = [
    (
        "MACRO_RATES",
        (
            "cpi", "pce", "fomc", "powell", "fed speaks", "fed chair",
            "rate hike", "rate cut", "interest rate", "inflation",
            "higher-for-longer", "sticky inflation", "real yield",
        ),
    ),
    (
        "GEOPOLITICAL",
        (
            "war", "sanction", "tariff", "election", "geopolit",
            "military", "missile", "invasion", "trade war", "policy risk",
        ),
    ),
    (
        "CROSS_ASSET",
        (
            "dxy", "dollar index", "stronger dollar", "usd strength",
            "us10y", "10y yield", "yield spike", "crude", "oil spike",
            "brent", "wti", "dollar strength", "stronger dollar",
        ),
    ),
    (
        "BINARY_EVENT",
        (
            "earnings", "reports in", "fda", "pdufa", "product launch",
            "guidance", "outlook", "ipo", "acquisition", "merger",
            "known event",
        ),
    ),
    (
        "SMART_MONEY",
        (
            "insider sell", "insider selling", "form 4", "analyst downgrade",
            "price target cut", "short interest", "heavily shorted",
            "days to cover", "put-heavy", "high p/c", "institutional selling",
            "betting against",
        ),
    ),
    (
        "TECHNICAL",
        (
            "rsi", "hmm", "overbought", "oversold", "breakout", "breakdown",
            "pullback", "cooler reading", "momentum", "moving average",
            "support", "resistance", "plan break", "walk away",
        ),
    ),
]

_EVENT_TYPE_TO_CATEGORY: dict[str, str] = {
    "EARNINGS_CALENDAR": "BINARY_EVENT",
    "POST_EARNINGS": "BINARY_EVENT",
    "EARNINGS": "BINARY_EVENT",
    "FDA": "BINARY_EVENT",
    "PDUFA": "BINARY_EVENT",
    "PRODUCT_LAUNCH": "BINARY_EVENT",
    "GUIDANCE_RAISE": "BINARY_EVENT",
    "GUIDANCE_CUT": "BINARY_EVENT",
    "CPI": "MACRO_RATES",
    "PCE": "MACRO_RATES",
    "FOMC": "MACRO_RATES",
    "NFP": "MACRO_RATES",
    "FED": "MACRO_RATES",
    "INSIDER": "SMART_MONEY",
    "ANALYST_DOWNGRADE": "SMART_MONEY",
    "SHORT_INTEREST": "SMART_MONEY",
    "GEOPOLITICAL": "GEOPOLITICAL",
    "TARIFF": "GEOPOLITICAL",
}


@dataclass(frozen=True)
class MappedDriver:
    category: str
    plain_english: str
    headline: str
    source: str
    priority: int
    direction: str = "neutral"  # bullish | bearish | neutral
    score: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def classify_text(text: str, *, event_type: str | None = None) -> str:
    """Return one of the 6 category tags for a free-text catalyst."""
    et = (event_type or "").strip().upper()
    if et in _EVENT_TYPE_TO_CATEGORY:
        return _EVENT_TYPE_TO_CATEGORY[et]
    blob = (text or "").lower()
    for cat, kws in _KEYWORD_RULES:
        if any(k in blob for k in kws):
            return cat
    return "TECHNICAL"


def _direction_from_text(text: str, default: str = "neutral") -> str:
    low = (text or "").lower()
    bear = (
        "sell", "dump", "downgrade", "cut", "bear", "war", "sanction",
        "tariff", "spike", "pressure", "breakdown", "overbought", "hike",
        "drag", "betting against",
    )
    bull = ("upgrade", "raise", "launch", "approval", "beat", "breakout", "bull")
    if any(w in low for w in bear):
        return "bearish"
    if any(w in low for w in bull):
        return "bullish"
    return default


def _days_until(text: str) -> int | None:
    m = re.search(r"in\s+(\d+)\s+days?", text or "", flags=re.IGNORECASE)
    if m:
        return int(m.group(1))
    return None


def map_catalyst_like(
    *,
    name: str = "",
    mechanism: str = "",
    event_type: str | None = None,
    direction: str | None = None,
    source: str = "catalyst",
    boost: float = 0.0,
) -> MappedDriver:
    text = f"{name} {mechanism}".strip()
    cat = classify_text(text, event_type=event_type)
    days = _days_until(text)
    score = float(CATEGORY_PRIORITY[cat]) + boost
    if cat == "BINARY_EVENT" and days is not None:
        if days <= 7:
            score += 25
        elif days <= 21:
            score += 10
    headline = (mechanism or name or "Unnamed catalyst").strip()
    for prefix in ("News:", "Known event:", "Known Event:"):
        if headline.startswith(prefix):
            headline = headline[len(prefix):].strip()
    return MappedDriver(
        category=cat,
        plain_english=PLAIN_ENGLISH[cat],
        headline=headline[:180],
        source=source,
        priority=int(score),
        direction=(direction or _direction_from_text(text)),
        score=score,
    )


def drivers_from_news_events(news_events: Iterable[dict] | None) -> list[MappedDriver]:
    out: list[MappedDriver] = []
    for card in news_events or []:
        if not isinstance(card, dict):
            continue
        out.append(
            map_catalyst_like(
                name=str(card.get("name") or ""),
                mechanism=str(card.get("mechanism") or card.get("title") or ""),
                event_type=str(card.get("event_type") or card.get("type") or "") or None,
                direction=str(card.get("direction") or "") or None,
                source="news_event",
                boost=5.0,
            )
        )
    return out


def drivers_from_catalyst_objects(cats: Iterable[Any] | None) -> list[MappedDriver]:
    out: list[MappedDriver] = []
    for c in cats or []:
        name = str(getattr(c, "name", "") or "")
        mech = str(getattr(c, "mechanism", "") or "")
        direction = str(getattr(c, "direction", "") or "")
        if direction == "breaks":
            direction = "bearish"
        elif direction == "unlocks":
            direction = "bullish"
        else:
            direction = _direction_from_text(f"{name} {mech}")
        out.append(
            map_catalyst_like(
                name=name,
                mechanism=mech,
                direction=direction,
                source="catalyst",
            )
        )
    return out


def _hmm_pct(packet: Any) -> float | None:
    for attr in ("hmm_bull_pct", "hmm_bull_probability"):
        v = getattr(packet, attr, None)
        if v is not None:
            try:
                return float(v)
            except (TypeError, ValueError):
                return None
    return None


def drivers_from_packet_signals(packet: Any) -> list[MappedDriver]:
    """Synthesize drivers from packet fields when explicit news is thin."""
    out: list[MappedDriver] = []
    rsi = getattr(packet, "rsi", None)
    hmm = _hmm_pct(packet)
    opts = str(getattr(packet, "options_class", None) or "").lower()
    sens_raw = getattr(packet, "sensitivities", None) or []
    sens = [str(s).lower() for s in sens_raw]

    if rsi is not None:
        try:
            rsi_f = float(rsi)
        except (TypeError, ValueError):
            rsi_f = None
        if rsi_f is not None and rsi_f >= 70:
            out.append(
                map_catalyst_like(
                    name="Overbought tape",
                    mechanism=f"Price ran hot (reading ~{rsi_f:.0f}) — don't chase.",
                    direction="bearish",
                    source="rsi",
                    boost=5.0,
                )
            )
    if hmm is not None and hmm <= 25:
        out.append(
            map_catalyst_like(
                name="Weak momentum regime",
                mechanism="Momentum is weak — overall signal is cautious.",
                direction="bearish",
                source="hmm",
                boost=8.0,
            )
        )
    if "put" in opts:
        out.append(
            map_catalyst_like(
                name="Put-heavy options",
                mechanism="Big traders are betting against this stock.",
                direction="bearish",
                source="options",
                boost=12.0,
            )
        )
    for s in sens:
        if any(k in s for k in ("usd", "dollar", "dxy")):
            out.append(
                map_catalyst_like(
                    name="Dollar pressure",
                    mechanism="Broader market drag from a strong dollar.",
                    direction="bearish",
                    source="sensitivity",
                    boost=8.0,
                )
            )
        if any(k in s for k in ("yield", "rate", "duration")):
            out.append(
                map_catalyst_like(
                    name="Rate sensitivity",
                    mechanism="Broader market drag from interest rates.",
                    direction="bearish",
                    source="sensitivity",
                    boost=10.0,
                )
            )
        if "oil" in s or "energy" in s:
            out.append(
                map_catalyst_like(
                    name="Oil / energy link",
                    mechanism="Market-wide pressure from energy prices.",
                    direction="neutral",
                    source="sensitivity",
                    boost=6.0,
                )
            )
        if any(k in s for k in ("geo", "politic", "tariff")):
            out.append(
                map_catalyst_like(
                    name="Policy / geopolitics",
                    mechanism="Political and global news is a risk factor.",
                    direction="bearish",
                    source="sensitivity",
                    boost=10.0,
                )
            )
    return out


def drivers_from_context(context: dict[str, Any] | None) -> list[MappedDriver]:
    """Optional live feeds: macro snapshot, insider, short interest, calendar."""
    if not context:
        return []
    out: list[MappedDriver] = []

    macro = context.get("macro") or {}
    if isinstance(macro, dict):
        cpi = macro.get("cpi_yoy") or macro.get("cpi")
        dgs10 = macro.get("dgs10") or macro.get("yield_10y") or macro.get("10y_yield")
        dxy = macro.get("dxy")
        fed = macro.get("fed_funds") or macro.get("fed_rate")
        if cpi is not None:
            try:
                cpi_f = float(cpi)
            except (TypeError, ValueError):
                cpi_f = None
            if cpi_f is not None and cpi_f >= 3.5:
                out.append(
                    map_catalyst_like(
                        name="Sticky inflation",
                        mechanism=f"Inflation still elevated (~{cpi_f:.1f}% YoY) — rate drag risk.",
                        direction="bearish",
                        source="macro_cpi",
                        boost=15.0,
                    )
                )
        if dgs10 is not None:
            try:
                y = float(dgs10)
            except (TypeError, ValueError):
                y = None
            if y is not None and y >= 4.25:
                out.append(
                    map_catalyst_like(
                        name="High 10Y yields",
                        mechanism=f"10-year yields near {y:.2f}% — broader market pressure.",
                        direction="bearish",
                        source="macro_yield",
                        boost=12.0,
                    )
                )
        if dxy is not None:
            try:
                d = float(dxy)
            except (TypeError, ValueError):
                d = None
            if d is not None and d >= 105:
                out.append(
                    map_catalyst_like(
                        name="Strong dollar",
                        mechanism=f"Dollar index elevated (~{d:.1f}) — market-wide pressure.",
                        direction="bearish",
                        source="macro_dxy",
                        boost=10.0,
                    )
                )
        if fed is not None:
            try:
                f = float(fed)
            except (TypeError, ValueError):
                f = None
            if f is not None and f >= 4.5:
                out.append(
                    map_catalyst_like(
                        name="Restrictive Fed policy",
                        mechanism="Fed policy still tight — inflation & rates backdrop matters.",
                        direction="bearish",
                        source="macro_fed",
                        boost=8.0,
                    )
                )

    insider = context.get("insider") or {}
    if isinstance(insider, dict):
        net = insider.get("net_sentiment") or insider.get("signal")
        sells = insider.get("sell_count") or insider.get("sells")
        sell_n = None
        try:
            sell_n = int(sells) if sells is not None else None
        except (TypeError, ValueError):
            sell_n = None
        if str(net).lower() in ("bearish", "selling", "sell") or (sell_n is not None and sell_n >= 3):
            out.append(
                map_catalyst_like(
                    name="Insider selling",
                    mechanism="Company insiders are selling shares.",
                    direction="bearish",
                    source="insider",
                    boost=20.0,
                )
            )

    si = context.get("short_interest") or {}
    if isinstance(si, dict):
        pct = si.get("short_pct") or si.get("shortPercentOfFloat")
        if pct is not None:
            try:
                pct_f = float(pct)
            except (TypeError, ValueError):
                pct_f = None
            if pct_f is not None:
                if pct_f > 1.0:
                    pct_f = pct_f / 100.0
                if pct_f >= 0.15:
                    out.append(
                        map_catalyst_like(
                            name="Elevated short interest",
                            mechanism=(
                                f"Short interest ~{pct_f * 100:.0f}% of float — "
                                "big traders are leaning short."
                            ),
                            direction="bearish",
                            source="short_interest",
                            boost=18.0,
                        )
                    )

    calendar = context.get("economic_calendar") or context.get("events") or []
    if isinstance(calendar, list):
        for ev in calendar[:6]:
            if not isinstance(ev, dict):
                continue
            title = str(ev.get("title") or ev.get("event") or ev.get("name") or "")
            et = str(ev.get("event_type") or ev.get("type") or "")
            out.append(
                map_catalyst_like(
                    name=title or et or "Macro event",
                    mechanism=title or et,
                    event_type=et or None,
                    source="economic_calendar",
                    boost=12.0,
                )
            )
    return out


def _dedupe(drivers: list[MappedDriver]) -> list[MappedDriver]:
    seen: set[str] = set()
    out: list[MappedDriver] = []
    for d in sorted(drivers, key=lambda x: x.score, reverse=True):
        key = f"{d.category}|{d.headline[:60].lower()}"
        if key in seen:
            continue
        seen.add(key)
        out.append(d)
    return out


def build_driver_board(
    packet: Any | None = None,
    cats: Iterable[Any] | None = None,
    *,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Ranked driver board for trading notes.

    Returns primary_driver, top_drivers (<=3), by_category, category_counts.
    """
    drivers: list[MappedDriver] = []
    if packet is not None:
        news = getattr(packet, "news_events", None)
        drivers.extend(drivers_from_news_events(news))
        drivers.extend(drivers_from_packet_signals(packet))
        pkt_ctx = getattr(packet, "driver_context", None)
        if isinstance(pkt_ctx, dict) and pkt_ctx:
            drivers.extend(drivers_from_context(pkt_ctx))
    drivers.extend(drivers_from_catalyst_objects(cats))
    drivers.extend(drivers_from_context(context))
    ranked = _dedupe(drivers)

    if ranked:
        primary = ranked[0]
    else:
        primary = MappedDriver(
            category="TECHNICAL",
            plain_english=PLAIN_ENGLISH["TECHNICAL"],
            headline="No fresh catalyst — this wait is about price and support.",
            source="default",
            priority=CATEGORY_PRIORITY["TECHNICAL"],
            direction="neutral",
            score=float(CATEGORY_PRIORITY["TECHNICAL"]),
        )

    by_cat: dict[str, list[dict[str, Any]]] = {k: [] for k in CATEGORY_PRIORITY}
    for d in ranked:
        by_cat.setdefault(d.category, []).append(d.as_dict())

    return {
        "primary_driver": primary.as_dict(),
        "top_drivers": [d.as_dict() for d in ranked[:3]],
        "by_category": by_cat,
        "category_counts": {k: len(v) for k, v in by_cat.items()},
        "matrix_version": "v1",
    }


def primary_driver_plain(board: dict[str, Any] | None) -> str:
    if not board:
        return "No fresh catalyst in the packet"
    pd = board.get("primary_driver") or {}
    label = pd.get("plain_english") or PLAIN_ENGLISH.get(str(pd.get("category") or ""), "Catalyst")
    headline = str(pd.get("headline") or "").strip()
    if not headline:
        return str(label)
    return f"{label}: {headline}"
