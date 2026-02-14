"""
Finnhub client: quote (last close) and analyst recommendation for indicator comparison.
Config: data.finnhub_apikey in config.yaml (note: apikey not api_key).
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

FINNHUB_BASE = "https://finnhub.io/api/v1"

# Map Finnhub recommendation to our bias for comparison
_FINNHUB_TO_BIAS = {
    "strongBuy": "Bullish",
    "buy": "Bullish",
    "hold": "Neutral",
    "sell": "Bearish",
    "strongSell": "Bearish",
}


def get_api_key(config: dict) -> str | None:
    return (config.get("data") or {}).get("finnhub_apikey") or config.get("finnhub_apikey") or None


def _request(config: dict, path: str, params: dict | None = None) -> dict | None:
    api_key = get_api_key(config)
    if not api_key or not str(api_key).strip():
        return None
    import urllib.parse
    import urllib.request
    q = dict(params or {})
    q["token"] = api_key.strip()
    url = f"{FINNHUB_BASE}{path}?{urllib.parse.urlencode(q)}"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            import json
            return json.loads(resp.read().decode())
    except Exception as e:
        logger.debug("Finnhub %s: %s", path, e)
        return None


def fetch_quote(config: dict, ticker: str) -> float | None:
    """Previous close (pc) or current price (c). Returns None on error."""
    data = _request(config, "/quote", {"symbol": ticker.upper()})
    if not isinstance(data, dict):
        return None
    # Prefer previous close for EOD comparison; fallback to current
    pc = data.get("pc")
    if pc is not None:
        try:
            return float(pc)
        except (TypeError, ValueError):
            pass
    c = data.get("c")
    if c is not None:
        try:
            return float(c)
        except (TypeError, ValueError):
            pass
    return None


def fetch_recommendation(config: dict, ticker: str) -> tuple[str | None, str | None]:
    """
    Analyst recommendation. Returns (bias_for_compare, display_label) or (None, None).
    bias: Bullish | Neutral | Bearish. label: e.g. "Buy"
    """
    data = _request(config, "/stock/recommendation", {"symbol": ticker.upper()})
    if not isinstance(data, list) or len(data) == 0:
        return None, None
    # Latest recommendation (first element is most recent)
    row = data[0] if isinstance(data[0], dict) else None
    if not row:
        return None, None
    # Finnhub returns strongBuy, buy, hold, sell, strongSell counts; take majority
    best_k, best_count = None, -1
    for k in ("strongBuy", "buy", "hold", "sell", "strongSell"):
        c = row.get(k)
        if c is not None:
            try:
                cnt = int(c)
                if cnt > best_count:
                    best_count = cnt
                    best_k = k
            except (TypeError, ValueError):
                pass
    if not best_k or best_k not in _FINNHUB_TO_BIAS:
        return None, None
    label = best_k.replace("strong", "Strong ").replace("Sell", "Sell").replace("Buy", "Buy")
    return _FINNHUB_TO_BIAS[best_k], label
