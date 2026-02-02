"""
CFTC Commitment of Traders (COT) client.
Free public data: https://publicreporting.cftc.gov/resource/6dca-aqww
Fetches speculative (non-commercial) positioning for gold, silver, crude oil.
Flags extreme positioning as contrarian reversal risk.
"""
from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from typing import Any

logger = logging.getLogger("signals.cot_client")

# CFTC public Socrata API – no API key required
COT_BASE = "https://publicreporting.cftc.gov/resource/6dca-aqww.json"

# Commodities we care about (CFTC commodity_name)
COT_COMMODITIES = [
    ("GOLD", "Gold"),
    ("SILVER", "Silver"),
    ("CRUDE OIL", "Crude oil"),
]

# Spec positioning as % of open interest above this = "extreme" (reversal risk)
EXTREME_LONG_PCT = 45.0
EXTREME_SHORT_PCT = 45.0


def fetch_cot_latest(commodity_name: str, limit: int = 1) -> tuple[list[dict], str | None]:
    """
    Fetch latest COT report row(s) for a commodity.
    Returns (list of rows, error). Uses CFTC public API; no key needed.
    Orders by report date desc then open interest desc to prefer main contract (e.g. COMEX Gold vs Micro).
    """
    # SoQL: filter by commodity_name, order by report date then open interest (main contract first)
    where_clause = f"commodity_name = '{commodity_name}'"
    order = "report_date_as_yyyy_mm_dd DESC, open_interest_all DESC"
    params = {
        "$where": where_clause,
        "$order": order,
        "$limit": str(limit),
    }
    query = urllib.parse.urlencode(params)
    url = f"{COT_BASE}?{query}"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
    except Exception as e:
        logger.debug("CFTC COT request failed for %s: %s", commodity_name, e)
        return [], str(e)
    if not isinstance(data, list):
        return [], "Unexpected response"
    return data, None


def _pct(row: dict, key: str) -> float | None:
    """Parse percentage field as float."""
    val = row.get(key)
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def get_cot_spec_positioning(commodity_name: str = "GOLD") -> tuple[dict | None, str | None]:
    """
    Get latest speculative (non-commercial) positioning for one commodity.
    Returns (summary, error) with keys: commodity_name, label, spec_long_pct, spec_short_pct,
    extreme ("long" | "short" | None), report_date.
    """
    rows, err = fetch_cot_latest(commodity_name, limit=1)
    if err or not rows:
        return None, err or "No data"
    row = rows[0]
    long_pct = _pct(row, "pct_of_oi_noncomm_long_all")
    short_pct = _pct(row, "pct_of_oi_noncomm_short_all")
    report_date = row.get("report_date_as_yyyy_mm_dd")
    if isinstance(report_date, str) and "T" in report_date:
        report_date = report_date.split("T")[0]

    label = next((lbl for name, lbl in COT_COMMODITIES if name == commodity_name), commodity_name)
    extreme = None
    if long_pct is not None and long_pct >= EXTREME_LONG_PCT:
        extreme = "long"
    elif short_pct is not None and short_pct >= EXTREME_SHORT_PCT:
        extreme = "short"

    return {
        "commodity_name": commodity_name,
        "label": label,
        "spec_long_pct": long_pct,
        "spec_short_pct": short_pct,
        "extreme": extreme,
        "report_date": report_date,
    }, None


def get_cot_extremes_for_guidelines() -> list[dict[str, Any]]:
    """
    Fetch COT for GOLD, SILVER, CRUDE OIL and return list of extremes for guidelines.
    Returns list of {label, extreme: "long"|"short", spec_long_pct, spec_short_pct}
    when positioning is extreme (reversal risk).
    """
    result = []
    for commodity_name, label in COT_COMMODITIES:
        summary, err = get_cot_spec_positioning(commodity_name)
        if err or not summary or not summary.get("extreme"):
            continue
        result.append({
            "label": label,
            "extreme": summary["extreme"],
            "spec_long_pct": summary.get("spec_long_pct"),
            "spec_short_pct": summary.get("spec_short_pct"),
        })
    return result


def get_cftc_cot(config: dict, symbol: str = "gold") -> tuple[dict | None, str | None]:
    """
    CFTC COT for a given symbol (gold, silver, crude).
    Compatible with data_source_stubs signature; config unused (API is public).
    Returns (summary dict, error).
    """
    name = symbol.upper()
    if name == "GOLD":
        commodity = "GOLD"
    elif name in ("SILVER", "SLV"):
        commodity = "SILVER"
    elif name in ("CRUDE", "OIL", "USO", "CL"):
        commodity = "CRUDE OIL"
    else:
        commodity = "GOLD"
    return get_cot_spec_positioning(commodity)
