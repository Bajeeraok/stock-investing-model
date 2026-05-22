"""
Batch catalyst flags onto dashboard signal rows (FMP news + detector).
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def enrich_results_catalysts(
    config: dict,
    results: list[dict[str, Any]],
    *,
    max_tickers: int = 17,
) -> None:
    """
    Mutates each result with optional catalyst: { active, top_event_type, top_impact, headline_summary }.
    """
    cfg = config.get("dashboard_catalysts") or {}
    if cfg.get("enabled") is False:
        return
    try:
        max_n = int(cfg.get("max_tickers", max_tickers))
    except (TypeError, ValueError):
        max_n = max_tickers

    from signals.fmp_client import fetch_stock_news, get_api_key

    if not get_api_key(config):
        return

    rows = [r for r in results if not r.get("error") and r.get("ticker")]
    for r in rows[:max_n]:
        t = str(r.get("ticker") or "")
        if not t:
            continue
        try:
            summary, err = fetch_stock_news(config, t, limit=12)
            if err or not summary:
                continue
            cat = summary.get("catalyst")
            if isinstance(cat, dict) and cat.get("active"):
                r["catalyst"] = {
                    "active": True,
                    "top_event_type": cat.get("top_event_type"),
                    "top_impact": cat.get("top_impact"),
                    "headline_summary": cat.get("headline_summary"),
                    "override_note": cat.get("override_note"),
                    "hours_since_catalyst": cat.get("hours_since_catalyst"),
                }
        except Exception as e:
            logger.debug("catalyst_batch %s: %s", t, e)
