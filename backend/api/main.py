"""
FastAPI backend for Stock Investing Model dashboard.
Run from backend folder: cd backend && uvicorn api.main:app --reload --port 8002
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo  # type: ignore

EST = ZoneInfo("America/New_York")


class ESTFormatter(logging.Formatter):
    """Format log timestamps in Eastern (EST/EDT)."""
    def formatTime(self, record, datefmt=None):
        dt = datetime.fromtimestamp(record.created, tz=EST)
        fmt = datefmt or self.datefmt or "%Y-%m-%d %H:%M:%S"
        return dt.strftime(fmt)


# Configure logging with EST timestamps
_handler = logging.StreamHandler(sys.stdout)
_handler.setFormatter(ESTFormatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
logging.basicConfig(level=logging.INFO, handlers=[_handler])
logger = logging.getLogger("api")

logger.info("Backend starting: setting up paths...")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logger.info("Backend: importing FastAPI and middleware...")
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

logger.info("Backend: importing dashboard router...")
from api.routers import dashboard, chat

logger.info("Backend: imports complete.")


class RequestLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        logger.info("→ %s %s", request.method, request.url.path)
        try:
            response = await call_next(request)
            logger.info("← %s %s %s", request.method, request.url.path, response.status_code)
            return response
        except Exception as e:
            logger.exception("← %s %s ERROR: %s", request.method, request.url.path, e)
            raise


app = FastAPI(
    title="Stock Investing Model API",
    description="Decision-support dashboard for retail investors",
    version="1.0.0",
)

_cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:3001,http://127.0.0.1:3000,http://127.0.0.1:3001")
app.add_middleware(RequestLogMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(dashboard.router, prefix="/api", tags=["dashboard"])
app.include_router(chat.router, prefix="/api", tags=["chat"])


@app.on_event("startup")
def startup():
    logger.info("FastAPI server startup complete. Listening for requests on /api/*")


@app.get("/api/health")
def health():
    return {"status": "ok", "timestamp": datetime.now().isoformat()}
