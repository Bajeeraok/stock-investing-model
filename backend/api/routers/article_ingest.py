"""
Manual article ingest — receives clips from the personal bookmarklet described in
docs/operations/ARTICLE_CLIPPER_BOOKMARKLET.md (e.g. a CNBC Investing Club analysis piece the
user is personally reading) and feeds them into the same catalyst pipeline FMP headlines
already use (signals/manual_catalysts.py -> catalyst_detector.build_catalyst_note_cards).

The bookmarklet runs cross-origin (on whatever site the user is reading) and deliberately posts
with Content-Type: text/plain in `mode: "no-cors"` — a custom header or `application/json`
content-type would force a CORS preflight that a third-party origin can't satisfy against this
app's restrictive CORS_ORIGINS policy (api/main.py). `no-cors` + a CORS-safelisted content-type
lets the browser send the request regardless, at the cost of the caller being unable to read
the response — acceptable for a fire-and-forget personal clip. That's also why the shared
secret travels in the JSON body rather than a header (a header would force the same preflight).

Env:
  ARTICLE_INGEST_SECRET — if set, required as body field "secret". Same env-var-gated-secret
  spirit as WEB_PUSH_ADMIN_SECRET (push.py), just body-based instead of header-based here.
"""
from __future__ import annotations

import json
import logging
import os

from fastapi import APIRouter, HTTPException, Request

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ingest", tags=["ingest"])


@router.post("/article")
async def ingest_article(request: Request) -> dict:
    try:
        payload = json.loads(await request.body())
    except Exception:
        raise HTTPException(status_code=400, detail="Body must be JSON")
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Body must be a JSON object")

    secret = (os.getenv("ARTICLE_INGEST_SECRET") or "").strip()
    if secret and str(payload.get("secret") or "").strip() != secret:
        raise HTTPException(status_code=403, detail="Invalid or missing secret")

    ticker = str(payload.get("ticker") or "").strip()
    title = str(payload.get("title") or "").strip()
    text = str(payload.get("text") or "").strip()
    if not ticker or not title or not text:
        raise HTTPException(status_code=400, detail="ticker, title, and text are required")

    from signals.manual_catalysts import add_manual_article

    try:
        row = add_manual_article(
            ticker,
            title=title,
            text=text,
            url=payload.get("url"),
            source=payload.get("source"),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    logger.info("[article_ingest] stored clip for %s: %s", ticker.upper(), title[:80])
    return {"status": "ok", "ticker": ticker.upper(), "submitted_at": row["submitted_at"]}
