"""
Persist inferred asset profiles for signal-universe tickers (JSON cache).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .constants import AssetType
from .models import AssetMeta

logger = logging.getLogger(__name__)

_CACHE_PATH = Path(__file__).resolve().parents[2] / "data" / "asset_registry_inferred.json"

_inferred_registry: dict[str, AssetMeta] | None = None


def cache_path() -> Path:
    return _CACHE_PATH


def meta_to_dict(meta: AssetMeta) -> dict[str, Any]:
    return {
        "ticker": meta.ticker,
        "name": meta.name,
        "asset_type": meta.asset_type.value,
        "sector": meta.sector,
        "country": meta.country,
        "beta": meta.beta,
        "insider_data_reliable": meta.insider_data_reliable,
        "fundamentals_applicable": meta.fundamentals_applicable,
        "ml_applicable": meta.ml_applicable,
        "macro_sensitive": meta.macro_sensitive,
        "macro_driver": meta.macro_driver,
        "geopolitical_risk": meta.geopolitical_risk,
        "sentiment_amplified": meta.sentiment_amplified,
        "insider_note": meta.insider_note,
        "fundamentals_note": meta.fundamentals_note,
        "ml_note": meta.ml_note,
    }


def meta_from_dict(d: dict[str, Any]) -> AssetMeta:
    raw_type = d.get("asset_type", AssetType.EQUITY_US.value)
    try:
        asset_type = AssetType(raw_type)
    except ValueError:
        asset_type = AssetType.EQUITY_US
    return AssetMeta(
        ticker=str(d.get("ticker") or "").upper(),
        name=str(d.get("name") or d.get("ticker") or ""),
        asset_type=asset_type,
        sector=str(d.get("sector") or "Unknown"),
        country=str(d.get("country") or "US"),
        beta=d.get("beta"),
        insider_data_reliable=bool(d.get("insider_data_reliable", True)),
        fundamentals_applicable=bool(d.get("fundamentals_applicable", True)),
        ml_applicable=bool(d.get("ml_applicable", True)),
        macro_sensitive=bool(d.get("macro_sensitive", False)),
        macro_driver=d.get("macro_driver"),
        geopolitical_risk=bool(d.get("geopolitical_risk", False)),
        sentiment_amplified=bool(d.get("sentiment_amplified", False)),
        insider_note=d.get("insider_note"),
        fundamentals_note=d.get("fundamentals_note"),
        ml_note=d.get("ml_note"),
    )


def _load_file() -> dict[str, Any]:
    path = cache_path()
    if not path.is_file():
        return {"version": 1, "updated_at": None, "tickers": {}}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except Exception as e:
        logger.warning("Could not load asset registry cache %s: %s", path, e)
    return {"version": 1, "updated_at": None, "tickers": {}}


def load_inferred_registry(force: bool = False) -> dict[str, AssetMeta]:
    global _inferred_registry
    if _inferred_registry is not None and not force:
        return _inferred_registry

    data = _load_file()
    tickers = data.get("tickers") or {}
    out: dict[str, AssetMeta] = {}
    if isinstance(tickers, dict):
        for sym, row in tickers.items():
            if isinstance(row, dict):
                try:
                    out[str(sym).upper()] = meta_from_dict(row)
                except Exception:
                    continue
    _inferred_registry = out
    return out


def get_inferred_meta(ticker: str) -> AssetMeta | None:
    sym = (ticker or "").upper().strip().replace(".", "-")
    return load_inferred_registry().get(sym)


def save_inferred_meta(meta: AssetMeta) -> None:
    """Upsert one ticker into the JSON cache."""
    path = cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = _load_file()
    tickers = data.setdefault("tickers", {})
    if not isinstance(tickers, dict):
        tickers = {}
        data["tickers"] = tickers
    tickers[meta.ticker] = meta_to_dict(meta)
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
    load_inferred_registry(force=True)


def save_inferred_batch(metas: dict[str, AssetMeta]) -> None:
    path = cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = _load_file()
    tickers = data.setdefault("tickers", {})
    if not isinstance(tickers, dict):
        tickers = {}
        data["tickers"] = tickers
    for sym, meta in metas.items():
        tickers[sym.upper()] = meta_to_dict(meta)
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
    load_inferred_registry(force=True)
