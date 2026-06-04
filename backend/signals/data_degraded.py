"""
Feature flags / degraded-mode surfacing when data vendors partially fail.
No new subscriptions — probes existing config keys and FMP plan check output.
"""
from __future__ import annotations

from typing import Any


def build_degraded_sources(
    config: dict | None,
    *,
    fmp_plan_status: dict | None = None,
) -> list[dict[str, str]]:
    """
    Returns list of { source, status, message } for dashboard trust strip.
    status: ok | degraded | unavailable
    """
    cfg = config or {}
    data_cfg = cfg.get("data") or {}
    flags_cfg = cfg.get("feature_flags") or {}
    out: list[dict[str, str]] = []

    fmp_key = (data_cfg.get("fmp_api_key") or cfg.get("fmp_api_key") or "").strip()
    if not fmp_key:
        out.append(
            {
                "source": "FMP",
                "status": "unavailable",
                "message": "No API key — calendar, insider list, and holder trend skipped.",
            }
        )
    elif fmp_plan_status and isinstance(fmp_plan_status, dict):
        unavailable = fmp_plan_status.get("unavailable") or []
        if unavailable:
            names = ", ".join(
                str(u.get("feature") or "feature")[:40]
                for u in unavailable[:4]
                if isinstance(u, dict)
            )
            out.append(
                {
                    "source": "FMP",
                    "status": "degraded",
                    "message": f"Some FMP endpoints failed ({names or 'plan limit'}). Yahoo fallbacks used where wired.",
                }
            )
        elif fmp_plan_status.get("has_key"):
            out.append({"source": "FMP", "status": "ok", "message": "Starter endpoints responding."})

    fred_key = (data_cfg.get("fred_api_key") or cfg.get("fred_api_key") or "").strip()
    if not fred_key:
        out.append(
            {
                "source": "FRED",
                "status": "degraded",
                "message": "No key — macro yield/CPI layers may use Yahoo proxies only.",
            }
        )
    elif flags_cfg.get("fred_disabled"):
        out.append({"source": "FRED", "status": "unavailable", "message": "Disabled via feature_flags.fred_disabled."})
    else:
        out.append({"source": "FRED", "status": "ok", "message": "Macro series available."})

    av_key = (data_cfg.get("alpha_vantage_api_key") or "").strip()
    if not av_key:
        out.append(
            {
                "source": "Alpha Vantage",
                "status": "degraded",
                "message": "News NLP uses FMP/Yahoo when AV absent.",
            }
        )

    if flags_cfg.get("yahoo_prices_disabled"):
        out.append(
            {"source": "Yahoo Finance", "status": "unavailable", "message": "Prices disabled via feature_flags."}
        )
    else:
        out.append({"source": "Yahoo Finance", "status": "ok", "message": "EOD prices and options proxies."})

    if flags_cfg.get("degraded_mode_force"):
        out.append(
            {
                "source": "Degraded mode",
                "status": "degraded",
                "message": str(flags_cfg.get("degraded_mode_note") or "Forced for testing."),
            }
        )

    return out


def degraded_mode_active(degraded_sources: list[dict[str, str]] | None) -> bool:
    if not degraded_sources:
        return False
    return any(d.get("status") in ("degraded", "unavailable") for d in degraded_sources if isinstance(d, dict))
