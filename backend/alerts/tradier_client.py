from __future__ import annotations

import os
import time
import logging
from dataclasses import dataclass

import requests

logger = logging.getLogger("alerts.tradier")


@dataclass(frozen=True)
class TradierConfig:
    token: str
    sandbox: bool = False
    rate_limit_calls: int = 60
    rate_limit_window_sec: int = 60
    timeout_sec: int = 12

    @property
    def base_url(self) -> str:
        return "https://sandbox.tradier.com/v1" if self.sandbox else "https://api.tradier.com/v1"


class TradierClient:
    """
    Minimal Tradier REST client for quotes + options chains.
    Uses a simple in-memory rate limiter (60 req/min dev plan).
    """

    def __init__(self, cfg: TradierConfig):
        self.cfg = cfg
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {cfg.token}",
                "Accept": "application/json",
            }
        )
        self._call_ts: list[float] = []

    @classmethod
    def from_env(cls) -> "TradierClient":
        token = os.getenv("TRADIER_TOKEN", "").strip()
        if not token:
            raise ValueError("Missing TRADIER_TOKEN env var")
        sandbox = os.getenv("TRADIER_SANDBOX", "false").lower() == "true"
        return cls(TradierConfig(token=token, sandbox=sandbox))

    def _rate_limit(self) -> None:
        now = time.time()
        win = self.cfg.rate_limit_window_sec
        self._call_ts = [t for t in self._call_ts if now - t < win]
        if len(self._call_ts) >= self.cfg.rate_limit_calls:
            sleep_for = win - (now - self._call_ts[0]) + 0.2
            if sleep_for > 0:
                logger.info("Rate limit reached — sleeping %.1fs", sleep_for)
                time.sleep(sleep_for)
        self._call_ts.append(time.time())

    def _get(self, endpoint: str, params: dict | None = None) -> dict:
        self._rate_limit()
        url = f"{self.cfg.base_url}{endpoint}"
        resp = self.session.get(url, params=params or {}, timeout=self.cfg.timeout_sec)
        if resp.status_code >= 400:
            try:
                payload = resp.json()
            except Exception:
                payload = {"text": resp.text[:400]}
            raise RuntimeError(f"Tradier {resp.status_code} {endpoint}: {payload}")
        return resp.json()

    def quotes(self, symbols: list[str]) -> dict:
        sym = ",".join([s.strip().upper() for s in symbols if s.strip()])
        return self._get("/markets/quotes", {"symbols": sym, "greeks": "true"})

    def options_expirations(self, symbol: str) -> dict:
        return self._get(
            "/markets/options/expirations",
            {"symbol": symbol.upper(), "includeAllRoots": "true", "strikes": "false"},
        )

    def options_chain(self, symbol: str, expiration: str, greeks: bool = True) -> dict:
        return self._get(
            "/markets/options/chains",
            {"symbol": symbol.upper(), "expiration": expiration, "greeks": str(greeks).lower()},
        )

