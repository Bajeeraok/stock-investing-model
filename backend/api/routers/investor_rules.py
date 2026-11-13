"""GET /api/investor-rules — investor rulebook with live ticker and market hits."""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from fastapi import APIRouter, Query

logger = logging.getLogger("api.investor_rules")
router = APIRouter()

_FACTORS_KEY = "investor_rules:macro_factors"
_SEEN_KEY = "investor_rules:first_seen"
_PAYLOAD_KEY = "investor_rules:payload"


def _macro_factors(config: dict) -> dict:
    from signals.cache import get_cached, set_cached

    hit = get_cached(_FACTORS_KEY)
    if isinstance(hit, dict):
        return hit
    try:
        from signals.macro_regime import fetch_macro_factors

        f = fetch_macro_factors(config) or {}
    except Exception as e:
        logger.warning("investor-rules macro factors: %s", e)
        f = {}
    set_cached(_FACTORS_KEY, f, 30 * 60)
    return f


def _seen_path():
    from config_loader import get_data_root

    return get_data_root() / "investor_rules_first_seen.json"


def _load_seen() -> dict[str, str]:
    from signals.cache import get_cached

    hit = get_cached(_SEEN_KEY)
    if isinstance(hit, dict):
        return hit
    try:
        p = _seen_path()
        if p.exists():
            return json.loads(p.read_text())
    except Exception:
        pass
    return {}


def _save_seen(seen: dict[str, str]) -> None:
    from signals.cache import set_cached

    set_cached(_SEEN_KEY, seen, 30 * 86400)
    try:
        p = _seen_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(seen))
    except Exception as e:
        logger.debug("investor-rules seen write: %s", e)


def build_investor_rules_payload() -> dict[str, Any]:
    from config_loader import load_config
    from signals.cache import get_cached, get_signals_panel, set_cached
    from signals.investor_rules import evaluate_rules, market_inputs
    from signals.time_et import today_est

    sp = get_signals_panel() or {}
    rows = [r for r in (sp.get("signals") or []) if isinstance(r, dict)]
    as_of = sp.get("as_of")
    cached = get_cached(_PAYLOAD_KEY)
    if isinstance(cached, dict) and cached.get("signals_as_of") == as_of and cached.get("n_tickers") == len(rows):
        return cached
    market = market_inputs(rows, _macro_factors(load_config()))
    seen = _load_seen()
    out = evaluate_rules(rows, market, first_seen=seen, today=str(today_est()))
    _save_seen(seen)
    out["signals_as_of"] = as_of
    set_cached(_PAYLOAD_KEY, out, 10 * 60)
    return out


@router.get("/investor-rules")
def get_investor_rules(ticker: Optional[str] = Query(None)):
    out = build_investor_rules_payload()
    if ticker:
        from signals.investor_rules import rules_for_ticker

        return {"ticker": ticker.upper(), "hits": rules_for_ticker(out, ticker), "signals_as_of": out.get("signals_as_of")}
    return out
