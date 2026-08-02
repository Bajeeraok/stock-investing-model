"""
WebSocket hub: push dashboard cache updates to connected browsers.

Sync workers (dashboard job, quote tick) call notify_dashboard_updated_sync();
the hub broadcasts on the FastAPI event loop.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect

logger = logging.getLogger("api.dashboard_hub")

_clients: set[WebSocket] = set()
_loop: asyncio.AbstractEventLoop | None = None
_last_event_at: float = 0.0
_min_interval_s = float((__import__("os").getenv("DASHBOARD_WS_MIN_INTERVAL_S") or "1").strip() or "1")


def set_event_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _loop
    _loop = loop


def _client_count() -> int:
    return len(_clients)


async def connect(websocket: WebSocket) -> None:
    await websocket.accept()
    _clients.add(websocket)
    logger.info("[dashboard-ws] client connected (%d total)", len(_clients))


def disconnect(websocket: WebSocket) -> None:
    _clients.discard(websocket)
    logger.info("[dashboard-ws] client disconnected (%d total)", len(_clients))


async def _broadcast(event: dict[str, Any]) -> None:
    if not _clients:
        return
    dead: list[WebSocket] = []
    for ws in list(_clients):
        try:
            await ws.send_json(event)
        except Exception:
            dead.append(ws)
    for ws in dead:
        disconnect(ws)


def notify_dashboard_updated_sync(
    kind: str,
    *,
    refresh_ts: str | None = None,
    quotes_updated_at: str | None = None,
    signals_updated_at: str | None = None,
    as_of_date: str | None = None,
) -> None:
    """Thread-safe: called from sync dashboard workers after Redis cache write."""
    global _last_event_at
    if not _clients:
        return
    now = time.monotonic()
    if now - _last_event_at < _min_interval_s:
        return
    _last_event_at = now

    event: dict[str, Any] = {
        "type": "dashboard_updated",
        "kind": kind,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    if refresh_ts:
        event["refresh_ts"] = refresh_ts
    if quotes_updated_at:
        event["quotes_updated_at"] = quotes_updated_at
    if signals_updated_at:
        event["signals_updated_at"] = signals_updated_at
    if as_of_date:
        event["as_of_date"] = as_of_date

    loop = _loop
    if loop is None or not loop.is_running():
        logger.debug("[dashboard-ws] no event loop — skip broadcast (%s)", kind)
        return
    try:
        asyncio.run_coroutine_threadsafe(_broadcast(event), loop)
    except Exception as exc:
        logger.debug("[dashboard-ws] broadcast schedule failed: %s", exc)


async def handle_websocket(websocket: WebSocket) -> None:
    await connect(websocket)
    try:
        while True:
            raw = await websocket.receive_text()
            if raw.strip().lower() == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.debug("[dashboard-ws] connection error: %s", exc)
    finally:
        disconnect(websocket)


def ws_public_url() -> str | None:
    """Public wss/ws URL for browsers when HTTP API is proxied through Next.js."""
    import os

    explicit = (os.getenv("DASHBOARD_WS_PUBLIC_URL") or "").strip().rstrip("/")
    if explicit:
        return explicit
    base = (os.getenv("PUBLIC_API_BASE_URL") or "").strip().rstrip("/")
    if not base:
        return None
    if base.startswith("https://"):
        return base.replace("https://", "wss://", 1) + "/api/dashboard/ws"
    if base.startswith("http://"):
        return base.replace("http://", "ws://", 1) + "/api/dashboard/ws"
    return f"wss://{base}/api/dashboard/ws"
