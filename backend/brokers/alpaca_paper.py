"""
Alpaca **paper** trading client (REST v2, plain ``requests``; no SDK dependency).

Enabled only when ``ALPACA_API_KEY`` and ``ALPACA_SECRET_KEY`` are set. The trading base
URL is pinned to the paper endpoint — this module cannot place live orders.
"""
from __future__ import annotations

import os
from typing import Any

import requests

PAPER_BASE_URL = "https://paper-api.alpaca.markets"
DATA_BASE_URL = "https://data.alpaca.markets"


class AlpacaNotConfigured(RuntimeError):
    pass


def alpaca_configured() -> bool:
    return bool(os.environ.get("ALPACA_API_KEY") and os.environ.get("ALPACA_SECRET_KEY"))


class AlpacaPaperClient:
    def __init__(
        self,
        api_key: str | None = None,
        secret_key: str | None = None,
        *,
        session: requests.Session | None = None,
        timeout: float = 15.0,
    ):
        self.api_key = api_key or os.environ.get("ALPACA_API_KEY")
        self.secret_key = secret_key or os.environ.get("ALPACA_SECRET_KEY")
        if not (self.api_key and self.secret_key):
            raise AlpacaNotConfigured("set ALPACA_API_KEY and ALPACA_SECRET_KEY to enable Alpaca paper trading")
        self.base_url = PAPER_BASE_URL
        self.session = session or requests.Session()
        self.timeout = timeout

    @property
    def _headers(self) -> dict[str, str]:
        return {"APCA-API-KEY-ID": self.api_key, "APCA-API-SECRET-KEY": self.secret_key}

    def _req(self, method: str, path: str, *, base: str | None = None, **kw) -> Any:
        r = self.session.request(method, f"{base or self.base_url}{path}", headers=self._headers, timeout=self.timeout, **kw)
        if r.status_code >= 400:
            raise RuntimeError(f"Alpaca {method} {path} -> HTTP {r.status_code}: {r.text[:300]}")
        return r.json() if r.content else None

    def account(self) -> dict:
        return self._req("GET", "/v2/account")

    def clock(self) -> dict:
        return self._req("GET", "/v2/clock")

    def positions(self) -> list[dict]:
        return self._req("GET", "/v2/positions")

    def orders(self, status: str = "open", limit: int = 100, after: str | None = None) -> list[dict]:
        params = {"status": status, "limit": limit, "direction": "desc"}
        if after:
            params["after"] = after
        return self._req("GET", "/v2/orders", params=params)

    def cancel_order(self, order_id: str) -> None:
        self._req("DELETE", f"/v2/orders/{order_id}")

    def submit_order(
        self,
        symbol: str,
        qty: int,
        side: str = "buy",
        *,
        order_type: str = "limit",
        limit_price: float | None = None,
        take_profit: float | None = None,
        stop_loss: float | None = None,
        time_in_force: str = "day",
        client_order_id: str | None = None,
    ) -> dict:
        """Whole-share order; adds a bracket (take-profit + stop-loss) when both are given."""
        if qty <= 0:
            raise ValueError("qty must be positive")
        if side not in ("buy", "sell"):
            raise ValueError("side must be buy or sell")
        body: dict[str, Any] = {
            "symbol": symbol.upper(),
            "qty": str(int(qty)),
            "side": side,
            "type": order_type,
            "time_in_force": time_in_force,
        }
        if order_type == "limit":
            if limit_price is None:
                raise ValueError("limit order needs limit_price")
            body["limit_price"] = f"{limit_price:.2f}"
        if take_profit is not None and stop_loss is not None:
            body["order_class"] = "bracket"
            body["take_profit"] = {"limit_price": f"{take_profit:.2f}"}
            body["stop_loss"] = {"stop_price": f"{stop_loss:.2f}"}
        if client_order_id:
            body["client_order_id"] = client_order_id[:48]
        return self._req("POST", "/v2/orders", json=body)

    def latest_bar(self, symbol: str, feed: str = "iex") -> dict | None:
        res = self._req("GET", f"/v2/stocks/{symbol.upper()}/bars/latest", base=DATA_BASE_URL, params={"feed": feed})
        return (res or {}).get("bar")


def plan_rebalance(
    picks: list[dict],
    equity: float,
    prices: dict[str, float],
    positions: dict[str, int],
    *,
    min_order_value: float = 100.0,
) -> list[dict]:
    """Whole-share buy/sell orders moving current positions to ``weight * equity`` per pick."""
    target = {}
    for p in picks:
        px = prices.get(p["ticker"])
        if px and px > 0:
            target[p["ticker"]] = int((float(p["weight"]) * equity) // px)
    orders = []
    for tk in sorted(set(target) | set(positions)):
        cur, want = int(positions.get(tk, 0)), int(target.get(tk, 0))
        diff = want - cur
        px = prices.get(tk) or 0.0
        if diff == 0 or abs(diff) * px < min_order_value:
            continue
        orders.append({"symbol": tk, "side": "buy" if diff > 0 else "sell", "qty": abs(diff), "ref_price": px})
    return orders
