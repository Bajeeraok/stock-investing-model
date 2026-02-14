"""
Polygon.io client: daily bars (close) for indicator comparison.
Config: data.polygon_api_key in config.yaml.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

POLYGON_BASE = "https://api.polygon.io"


def get_api_key(config: dict) -> str | None:
    return (config.get("data") or {}).get("polygon_api_key") or config.get("polygon_api_key") or None


def fetch_last_close(config: dict, ticker: str) -> float | None:
    """
    Fetch last daily close from Polygon aggs. Returns None on error or no key.
    """
    api_key = get_api_key(config)
    if not api_key or not str(api_key).strip():
        return None
    to_dt = datetime.now(timezone.utc)
    from_dt = to_dt - timedelta(days=10)
    to_str = to_dt.strftime("%Y-%m-%d")
    from_str = from_dt.strftime("%Y-%m-%d")
    url = f"{POLYGON_BASE}/v2/aggs/ticker/{ticker.upper()}/range/1/day/{from_str}/{to_str}?adjusted=true&limit=5&sort=desc"
    try:
        import urllib.request
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {api_key.strip()}"})
        with urllib.request.urlopen(req, timeout=12) as resp:
            import json
            data = json.loads(resp.read().decode())
    except Exception as e:
        logger.debug("Polygon aggs for %s: %s", ticker, e)
        return None
    if not isinstance(data, dict):
        return None
    results = data.get("results")
    if not isinstance(results, list) or len(results) == 0:
        return None
    close = results[0].get("c")
    if close is not None:
        try:
            return float(close)
        except (TypeError, ValueError):
            pass
    return None
