"""Dev tools — API catalog for ad-hoc runner UI."""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi import APIRouter

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.endpoint_catalog import get_endpoint_catalog

router = APIRouter()


@router.get("/dev/endpoints")
async def list_api_endpoints():
    """Curated list of API routes for dashboard ad-hoc runner."""
    items = get_endpoint_catalog()
    groups = sorted({e["group"] for e in items})
    return {
        "groups": groups,
        "count": len(items),
        "endpoints": items,
        "note": "Use Run in the Analysis tab or open paths in a new tab. POST/DELETE may mutate data.",
    }
