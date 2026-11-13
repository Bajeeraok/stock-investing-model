"""SEC 8-K event feed (free EDGAR submissions API) for the investor rulebook's story-change rule."""

from __future__ import annotations

import json
import logging
import time
from datetime import date, timedelta
from typing import Any

logger = logging.getLogger(__name__)

CACHE_KEY = "edgar_8k:latest"
CACHE_TTL = 3 * 86400
LOOKBACK_DAYS = 7

ITEM_LABELS = {
    "1.01": "Material agreement",
    "1.02": "Agreement terminated",
    "1.03": "Bankruptcy",
    "2.01": "Acquisition or sale completed",
    "2.02": "Earnings results",
    "2.03": "New debt obligation",
    "2.05": "Restructuring / exit costs",
    "2.06": "Impairment",
    "3.01": "Delisting notice",
    "3.02": "Unregistered share sale",
    "4.01": "Auditor change",
    "4.02": "Prior financials not reliable (restatement)",
    "5.01": "Change in control",
    "5.02": "Director or officer change",
    "5.07": "Shareholder vote",
    "7.01": "Reg FD disclosure",
    "8.01": "Other event",
}
# Items that can change the investment story (Lynch: sell when the story changes).
STORY_ITEMS = {"1.02", "1.03", "2.01", "2.05", "2.06", "3.01", "4.01", "4.02", "5.01", "5.02"}
SEVERE_ITEMS = {"1.03", "3.01", "4.02"}


def events_from_submissions(sub: dict, since: date) -> list[dict[str, Any]]:
    recent = (sub.get("filings") or {}).get("recent") or {}
    forms = recent.get("form") or []
    dates = recent.get("filingDate") or []
    items = recent.get("items") or []
    acc = recent.get("accessionNumber") or []
    cik = str(sub.get("cik") or "").lstrip("0")
    out = []
    for i, f in enumerate(forms):
        if f not in ("8-K", "8-K/A") or i >= len(dates):
            continue
        try:
            d = date.fromisoformat(dates[i])
        except ValueError:
            continue
        if d < since:
            continue
        codes = [c.strip() for c in (items[i] if i < len(items) else "").split(",") if c.strip()]
        story = [c for c in codes if c in STORY_ITEMS]
        out.append({
            "date": dates[i],
            "form": f,
            "items": codes,
            "labels": [ITEM_LABELS.get(c, f"Item {c}") for c in codes if c != "9.01"],
            "story": story,
            "severe": any(c in SEVERE_ITEMS for c in codes),
            "url": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=8-K" if cik else None,
            "accession": acc[i] if i < len(acc) else None,
        })
    return out


def run_scan(tickers: list[str], lookback_days: int = LOOKBACK_DAYS) -> dict[str, Any]:
    from signals.cache import set_cached
    from signals.edgar_insider import REQUEST_DELAY, SEC_DATA_BASE, _sec_request, get_ticker_to_cik
    from signals.time_et import now_iso_et

    since = date.today() - timedelta(days=lookback_days)
    ciks = get_ticker_to_cik(tickers)
    by_ticker: dict[str, list[dict]] = {}
    for t, cik in ciks.items():
        body, err = _sec_request(f"{SEC_DATA_BASE}/submissions/CIK{cik}.json")
        time.sleep(REQUEST_DELAY)
        if err or not body:
            continue
        try:
            ev = events_from_submissions(json.loads(body), since)
        except Exception:
            ev = []
        if ev:
            by_ticker[t] = ev
    out = {"as_of": now_iso_et(), "lookback_days": lookback_days, "n_checked": len(ciks), "events": by_ticker}
    set_cached(CACHE_KEY, out, CACHE_TTL)
    try:
        from config_loader import get_data_root

        (get_data_root() / "edgar_8k_latest.json").write_text(json.dumps(out))
    except Exception:
        pass
    logger.info("[edgar-8k] %d tickers with 8-Ks in %dd (of %d)", len(by_ticker), lookback_days, len(ciks))
    return out


def load_latest() -> dict[str, Any] | None:
    from signals.cache import get_cached

    hit = get_cached(CACHE_KEY)
    if isinstance(hit, dict):
        return hit
    try:
        from config_loader import get_data_root

        p = get_data_root() / "edgar_8k_latest.json"
        return json.loads(p.read_text()) if p.exists() else None
    except Exception:
        return None
