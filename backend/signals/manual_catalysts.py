"""
Manually-clipped articles (e.g. CNBC Investing Club analysis) fed into the same catalyst
pipeline FMP headlines already use — see docs/operations/ARTICLE_CLIPPER_BOOKMARKLET.md.

Persisted under DATA_ROOT/manual_catalysts.json, same read/write pattern as
behavior/trade_discipline.py. Advisory only — never mutates bands, gates, or scores,
same guarantee build_catalyst_note_cards() already makes for FMP-sourced cards.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from config_loader import get_data_root
from signals.time_et import now_iso_et

logger = logging.getLogger(__name__)

MAX_ARTICLES_PER_TICKER = 20
MAX_TEXT_CHARS = 20_000


def _path():
    return get_data_root() / "manual_catalysts.json"


def _load() -> dict[str, list[dict[str, Any]]]:
    p = _path()
    if not p.exists():
        return {}
    try:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.warning("manual_catalysts read failed: %s", e)
        return {}


def _save(data: dict[str, list[dict[str, Any]]]) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def add_manual_article(
    ticker: str,
    *,
    title: str,
    text: str,
    url: str | None = None,
    source: str | None = None,
) -> dict[str, Any]:
    """Store one clipped article, most-recent-first, capped per ticker."""
    sym = (ticker or "").strip().upper()
    if not sym:
        raise ValueError("ticker is required")
    title = (title or "").strip()[:300]
    text = (text or "").strip()[:MAX_TEXT_CHARS]
    if not title or not text:
        raise ValueError("title and text are required")

    row = {
        "title": title,
        "text": text,
        "url": (url or "").strip() or None,
        "source": (source or "").strip() or None,
        "submitted_at": now_iso_et(),
    }
    data = _load()
    articles = data.get(sym) or []
    articles.insert(0, row)
    data[sym] = articles[:MAX_ARTICLES_PER_TICKER]
    _save(data)
    return row


def _fallback_card(row: dict[str, Any], ticker: str) -> dict[str, Any]:
    """When build_catalyst_note_cards finds no matching event-type regex (likely for a
    long-form opinion/analysis piece rather than a hard-news wire item) — guarantee the
    user still sees their clip landed, instead of it silently vanishing."""
    from signals.catalyst_detector import _age_label, _article_age_hours, _extract_domain, _horizon_from_age

    sym = ticker.strip().upper()
    age_h = _article_age_hours(row.get("submitted_at"))
    age_l = _age_label(age_h)
    source = row.get("source") or _extract_domain(row.get("url"))
    source = source if source and source != "unknown" else ""
    title = row["title"]
    draft_bits = [f"{sym} · Analyst note (watch) — {title}"]
    meta = " · ".join(x for x in (source, age_l) if x)
    if meta:
        draft_bits.append(meta)
    draft_bits.append("Advisory only — does not change bands or gates.")
    return {
        "name": "Analyst Note",
        "event_type": "MANUAL_NOTE",
        "direction": "watch",
        "mechanism": title[:180],
        "watch": "price reaction vs your plan",
        "horizon": _horizon_from_age(age_h),
        "source": source or None,
        "age_hours": None if age_h >= 900 else age_h,
        "age_label": age_l or None,
        "url": row.get("url"),
        "headline_count": 1,
        "draft_note": " ".join(draft_bits)[:500],
    }


def manual_cards_for_ticker(ticker: str, *, max_cards: int = 2) -> list[dict[str, Any]]:
    """Cards from manually-clipped articles for this ticker, most-recent first.

    Tries the real event classifier first (build_catalyst_note_cards) so a clip that does
    mention e.g. an FDA approval still gets properly categorized; falls back to a generic
    "Analyst Note" card when nothing matches rather than dropping the submission silently.
    """
    sym = (ticker or "").strip().upper()
    articles = _load().get(sym) or []
    if not articles:
        return []

    from signals.catalyst_detector import build_catalyst_note_cards

    cards: list[dict[str, Any]] = []
    for row in articles:
        if len(cards) >= max_cards:
            break
        headline = {
            "title": row.get("title"),
            "text": row.get("text"),
            "published": row.get("submitted_at"),
            "url": row.get("url"),
        }
        matched = build_catalyst_note_cards([headline], ticker=sym, max_cards=1)
        card = matched[0] if matched else _fallback_card(row, sym)
        card["origin"] = "manual"
        cards.append(card)
    return cards
