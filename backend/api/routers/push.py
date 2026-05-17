"""
Web Push API — Stage 2 browser notifications.

Subscribe/unsubscribe stores PushSubscription JSON under DATA_ROOT.
Sending requires VAPID keys and optional WEB_PUSH_ADMIN_SECRET for POST /test.

Env:
  VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY — URL-safe base64 (generate: npx web-push generate-vapid-keys)
  VAPID_CLAIM_EMAIL — mailto: owner for VAPID claims (default mailto:alerts@localhost)
  WEB_PUSH_ADMIN_SECRET — if set, required as header X-Push-Admin-Secret for POST /api/push/test
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/push", tags=["push"])


def _subs_file() -> Path:
    from config_loader import get_data_root

    p = get_data_root() / "web_push_subscriptions.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _load_subscriptions() -> list[dict[str, Any]]:
    path = _subs_file()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.warning("web push subscriptions read failed: %s", e)
        return []


def _save_subscriptions(subs: list[dict[str, Any]]) -> None:
    path = _subs_file()
    path.write_text(json.dumps(subs, indent=2), encoding="utf-8")


def broadcast_web_push(title: str, body: str, url: str = "/") -> dict[str, Any]:
    """
    Send Web Push to all stored subscriptions (for future alert/EOD hooks).
    Returns {sent, failed, total, failed_endpoints?, skipped?, reason?}.
    """
    priv = (os.getenv("VAPID_PRIVATE_KEY") or "").strip()
    pub = (os.getenv("VAPID_PUBLIC_KEY") or "").strip()
    claim = (os.getenv("VAPID_CLAIM_EMAIL") or "mailto:alerts@localhost").strip()
    if not claim.startswith("mailto:"):
        claim = "mailto:" + claim
    if not priv or not pub:
        return {"sent": 0, "failed": 0, "total": 0, "skipped": True, "reason": "vapid_not_configured"}
    try:
        from pywebpush import WebPushException, webpush
    except ImportError:
        return {"sent": 0, "failed": 0, "total": 0, "skipped": True, "reason": "pywebpush_not_installed"}

    subs = _load_subscriptions()
    payload = json.dumps({"title": title, "body": body, "url": url})
    ok = 0
    failed: list[str] = []
    for sub in subs:
        try:
            webpush(
                subscription_info=sub,
                data=payload,
                vapid_private_key=priv,
                vapid_claims={"sub": claim},
            )
            ok += 1
        except WebPushException as e:
            logger.info("webpush failed: %s", e)
            failed.append(str(sub.get("endpoint", ""))[:48])
        except Exception as e:
            logger.warning("webpush error: %s", e)
            failed.append(str(sub.get("endpoint", ""))[:48])
    return {"sent": ok, "failed": len(failed), "total": len(subs), "failed_endpoints": failed[:5]}


@router.get("/public-config")
def public_config() -> dict[str, Any]:
    pub = (os.getenv("VAPID_PUBLIC_KEY") or "").strip()
    return {"enabled": bool(pub), "publicKey": pub or None}


class SubscribeBody(BaseModel):
    subscription: dict[str, Any] = Field(..., description="Browser PushSubscription.toJSON()")


@router.post("/subscribe")
def subscribe(body: SubscribeBody) -> dict[str, Any]:
    sub = body.subscription
    endpoint = (sub.get("endpoint") or "").strip()
    if not endpoint:
        raise HTTPException(status_code=400, detail="subscription.endpoint required")

    subs = _load_subscriptions()
    endpoints = {s.get("endpoint") for s in subs if isinstance(s.get("endpoint"), str)}
    if endpoint not in endpoints:
        subs.append(sub)
        _save_subscriptions(subs)
    return {"ok": True, "count": len(subs)}


class UnsubscribeBody(BaseModel):
    endpoint: str


@router.post("/unsubscribe")
def unsubscribe(body: UnsubscribeBody) -> dict[str, Any]:
    ep = (body.endpoint or "").strip()
    if not ep:
        raise HTTPException(status_code=400, detail="endpoint required")
    subs = [s for s in _load_subscriptions() if str(s.get("endpoint") or "") != ep]
    _save_subscriptions(subs)
    return {"ok": True, "count": len(subs)}


class TestBody(BaseModel):
    title: str = "Thrive Alpha"
    body: str = "Test notification"
    url: str = "/"


@router.post("/test")
def test_push(
    body: TestBody,
    x_push_admin_secret: str | None = Header(None, alias="X-Push-Admin-Secret"),
) -> dict[str, Any]:
    """Send a test push to all stored subscriptions (dev / ops)."""
    secret = (os.getenv("WEB_PUSH_ADMIN_SECRET") or "").strip()
    if secret and (x_push_admin_secret or "").strip() != secret:
        raise HTTPException(status_code=403, detail="Invalid or missing X-Push-Admin-Secret")

    if not (os.getenv("VAPID_PRIVATE_KEY") or "").strip() or not (os.getenv("VAPID_PUBLIC_KEY") or "").strip():
        raise HTTPException(status_code=503, detail="VAPID keys not configured")

    out = broadcast_web_push(body.title, body.body, body.url)
    if out.get("skipped"):
        raise HTTPException(status_code=503, detail=str(out.get("reason") or "push_unavailable"))
    return out
