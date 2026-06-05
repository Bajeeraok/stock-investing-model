"""
Pre-IPO / private company watch panel — curated reference, not tradable signals.

Valuations and status are config-maintained; optional public_proxies link to
names already in the dashboard signal universe for tape context.

News: FMP general-latest + proxy ticker news, filtered by company keywords.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

DEFAULT_PRE_IPO: list[dict[str, Any]] = [
    {
        "id": "spacex",
        "name": "SpaceX",
        "sector": "Aerospace",
        "last_valuation_usd_b": 350,
        "valuation_as_of": "2024-12",
        "status": "private",
        "note": "No public ticker. Watch launch cadence and defense/space read-through.",
        "public_proxies": ["RKLB", "BA"],
        "news_keywords": ["SpaceX", "Starship", "Starlink"],
    },
    {
        "id": "openai",
        "name": "OpenAI",
        "sector": "AI",
        "last_valuation_usd_b": 157,
        "valuation_as_of": "2024-10",
        "status": "private",
        "note": "Structurally private; MSFT/NVDA often used as AI-cycle proxies.",
        "public_proxies": ["MSFT", "NVDA"],
        "news_keywords": ["OpenAI", "ChatGPT", "Sam Altman"],
    },
    {
        "id": "anthropic",
        "name": "Anthropic",
        "sector": "AI",
        "last_valuation_usd_b": 61.5,
        "valuation_as_of": "2025-03",
        "status": "private",
        "note": "Google/Amazon-backed; no direct equity access for most retail.",
        "public_proxies": ["GOOGL", "AMZN"],
        "news_keywords": ["Anthropic", "Claude"],
    },
]

_PRE_IPO_THEME_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(funding|raised|series [a-e]|valuation|investment round|billion)\b", re.I), "Funding"),
    (re.compile(r"\b(ipo|goes public|direct listing|spac|listing)\b", re.I), "IPO"),
    (re.compile(r"\b(partnership|strategic deal|alliance|contract award)\b", re.I), "Partnership"),
    (re.compile(r"\b(regulat|antitrust|doj|ftc|ban|investigation)\b", re.I), "Regulation"),
    (re.compile(r"\b(layoff|restructur|workforce reduction|job cut)\b", re.I), "Restructuring"),
    (re.compile(r"\b(launch|orbit|satellite|rocket)\b", re.I), "Product"),
]


def pre_ipo_config(config: dict | None) -> dict[str, Any]:
    raw = (config or {}).get("pre_ipo_watchlist") or {}
    if not isinstance(raw, dict):
        return {"enabled": True, "fetch_news": True, "companies": list(DEFAULT_PRE_IPO)}
    companies = raw.get("companies")
    if not companies:
        companies = list(DEFAULT_PRE_IPO)
    return {
        "enabled": bool(raw.get("enabled", True)),
        "fetch_news": bool(raw.get("fetch_news", True)),
        "news_limit": int(raw.get("news_limit", 100)),
        "disclaimer": raw.get(
            "disclaimer",
            "Reference only — not tradable in this app. Valuations are manually maintained from public sources.",
        ),
        "companies": companies,
    }


def news_keywords_for_company(raw: dict[str, Any]) -> list[str]:
    kws: list[str] = []
    name = (raw.get("name") or "").strip()
    if name:
        kws.append(name)
    for k in raw.get("news_keywords") or []:
        if k and str(k).strip():
            kws.append(str(k).strip())
    # dedupe case-insensitive
    seen: set[str] = set()
    out: list[str] = []
    for k in kws:
        lk = k.lower()
        if lk not in seen:
            seen.add(lk)
            out.append(k)
    return out


def article_blob(item: dict[str, Any]) -> str:
    title = item.get("title") or item.get("headline") or ""
    body = item.get("text") or item.get("description") or item.get("content") or item.get("summary") or ""
    return f"{title} {body}".lower()


def article_matches_keywords(item: dict[str, Any], keywords: list[str]) -> bool:
    if not keywords:
        return False
    blob = article_blob(item)
    return any(kw.lower() in blob for kw in keywords)


def _parse_published_ts(item: dict[str, Any]) -> float:
    pub = item.get("publishedDate") or item.get("published_at") or item.get("date")
    if not pub:
        return 0.0
    s = str(pub).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(s[:19] if fmt != "%Y-%m-%d" else s[:10], fmt)
            return dt.replace(tzinfo=timezone.utc).timestamp()
        except ValueError:
            continue
    return 0.0


def dedupe_articles(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for item in articles:
        if not isinstance(item, dict):
            continue
        title = (item.get("title") or item.get("headline") or "").strip().lower()
        if not title or title in seen:
            continue
        seen.add(title)
        out.append(item)
    out.sort(key=_parse_published_ts, reverse=True)
    return out


def detect_pre_ipo_themes(articles: list[dict[str, Any]]) -> list[str]:
    themes: list[str] = []
    seen: set[str] = set()
    for item in articles[:8]:
        blob = article_blob(item)
        for pat, label in _PRE_IPO_THEME_PATTERNS:
            if pat.search(blob) and label not in seen:
                seen.add(label)
                themes.append(label)
    return themes


def format_headline_row(item: dict[str, Any]) -> dict[str, Any]:
    from signals.news_keyword_sentiment import article_url

    title = (item.get("title") or item.get("headline") or "").strip()
    url = article_url(item)
    pub = item.get("publishedDate") or item.get("published_at") or item.get("date")
    source = item.get("site") or item.get("source") or item.get("publisher") or ""
    if not source and url:
        try:
            source = urlparse(url).netloc.replace("www.", "")
        except Exception:
            source = ""
    return {
        "title": title[:160],
        "url": url or None,
        "published_at": str(pub) if pub else None,
        "source": str(source)[:80] if source else None,
    }


def build_pre_ipo_news_block(
    articles: list[dict[str, Any]],
    *,
    company_id: str,
    keywords: list[str],
    sources_note: str | None = None,
) -> dict[str, Any]:
    """Sentiment + headlines for one private name from pre-filtered articles."""
    if not articles:
        return {
            "available": False,
            "headline_count": 0,
            "message": f"No recent headlines matched: {', '.join(keywords[:3])}",
            "keywords": keywords,
        }

    from signals.fmp_client import _stock_news_summary_from_items

    summary = _stock_news_summary_from_items(articles, company_id, limit=min(10, len(articles)))
    rows = [format_headline_row(a) for a in articles[:5]]
    latest = rows[0] if rows else None
    themes = detect_pre_ipo_themes(articles)
    catalyst = summary.get("catalyst")
    catalyst_out = None
    if isinstance(catalyst, dict) and catalyst.get("active"):
        catalyst_out = {
            "headline_summary": catalyst.get("headline_summary"),
            "top_event_type": catalyst.get("top_event_type"),
            "top_impact": catalyst.get("top_impact"),
            "hours_since_catalyst": catalyst.get("hours_since_catalyst"),
        }

    return {
        "available": True,
        "headline_count": summary.get("headline_count") or len(articles),
        "sentiment_label": summary.get("sentiment_label"),
        "sentiment_score_avg": summary.get("sentiment_score_avg"),
        "sentiment_method": summary.get("sentiment_method"),
        "latest": latest,
        "headlines": rows,
        "themes": themes,
        "catalyst": catalyst_out,
        "keywords": keywords,
        "sources_note": sources_note,
    }


def _load_general_news(config: dict, limit: int) -> list[dict[str, Any]]:
    try:
        from signals.cache import cached_general_news
        from signals.fmp_client import fetch_general_news_latest, get_api_key

        if not get_api_key(config):
            return []

        def _fetch():
            rows, _err = fetch_general_news_latest(config, limit=limit)
            return rows

        return cached_general_news(_fetch) or []
    except Exception:
        return []


def _load_proxy_news(config: dict, ticker: str, limit: int = 12) -> list[dict[str, Any]]:
    try:
        from signals.cache import cached_stock_news_articles
        from signals.fmp_client import fetch_stock_news_articles, get_api_key

        if not get_api_key(config):
            return []

        sym = ticker.upper()

        def _fetch():
            rows, _err = fetch_stock_news_articles(config, sym, limit=limit)
            return rows

        return cached_stock_news_articles(sym, _fetch) or []
    except Exception:
        return []


def collect_company_news_articles(
    config: dict,
    raw: dict[str, Any],
    *,
    general_articles: list[dict[str, Any]] | None = None,
    news_limit: int = 100,
) -> tuple[list[dict[str, Any]], str]:
    """Merge general + proxy ticker news filtered by company keywords."""
    keywords = news_keywords_for_company(raw)
    if not keywords:
        return [], "no keywords"

    general = general_articles if general_articles is not None else _load_general_news(config, news_limit)
    matched = [a for a in general if article_matches_keywords(a, keywords)]

    proxy_sources: list[str] = []
    for tk in raw.get("public_proxies") or []:
        sym = str(tk).upper()
        if not sym:
            continue
        proxy_rows = _load_proxy_news(config, sym, limit=12)
        proxy_hits = [a for a in proxy_rows if article_matches_keywords(a, keywords)]
        if proxy_hits:
            proxy_sources.append(sym)
            matched.extend(proxy_hits)

    matched = dedupe_articles(matched)
    note_parts = ["FMP general news"]
    if proxy_sources:
        note_parts.append(f"proxy tickers ({', '.join(proxy_sources[:3])})")
    return matched, " · ".join(note_parts)


def build_pre_ipo_panel(
    config: dict | None,
    *,
    results_by_ticker: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Dashboard payload: curated private names + proxy scores + FMP news."""
    cfg = pre_ipo_config(config)
    if not cfg.get("enabled"):
        return {"enabled": False, "items": [], "disclaimer": cfg.get("disclaimer")}

    items: list[dict[str, Any]] = []
    lookup = {str(k).upper(): v for k, v in (results_by_ticker or {}).items() if isinstance(v, dict)}

    general_articles: list[dict] | None = None
    if cfg.get("fetch_news") and config:
        general_articles = _load_general_news(config, int(cfg.get("news_limit", 100)))

    for raw in cfg.get("companies") or []:
        if not isinstance(raw, dict) or not raw.get("name"):
            continue
        item = {
            "id": raw.get("id") or str(raw.get("name", "")).lower().replace(" ", "-"),
            "name": raw.get("name"),
            "sector": raw.get("sector"),
            "last_valuation_usd_b": _f(raw.get("last_valuation_usd_b")),
            "valuation_as_of": raw.get("valuation_as_of"),
            "status": (raw.get("status") or "private").lower(),
            "note": raw.get("note"),
            "public_proxies": [str(t).upper() for t in (raw.get("public_proxies") or []) if t],
        }
        proxy_signals: list[dict[str, Any]] = []
        for tk in item["public_proxies"]:
            r = lookup.get(tk)
            if not r or r.get("error"):
                continue
            proxy_signals.append(
                {
                    "ticker": tk,
                    "close": r.get("close"),
                    "composite_buy": r.get("composite_buy"),
                    "regime": r.get("regime"),
                    "signal": r.get("signal"),
                }
            )
        if proxy_signals:
            item["proxy_signals"] = proxy_signals

        if cfg.get("fetch_news") and config:
            articles, sources_note = collect_company_news_articles(
                config,
                raw,
                general_articles=general_articles,
                news_limit=int(cfg.get("news_limit", 100)),
            )
            item["news"] = build_pre_ipo_news_block(
                articles,
                company_id=str(item["id"]),
                keywords=news_keywords_for_company(raw),
                sources_note=sources_note,
            )

        items.append(item)

    return {
        "enabled": True,
        "disclaimer": cfg.get("disclaimer"),
        "items": items,
    }


def _f(x: Any) -> float | None:
    try:
        if x is None:
            return None
        return float(x)
    except (TypeError, ValueError):
        return None
