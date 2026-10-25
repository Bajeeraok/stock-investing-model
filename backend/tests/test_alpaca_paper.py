import json

import pytest

from brokers.alpaca_paper import PAPER_BASE_URL, AlpacaNotConfigured, AlpacaPaperClient, alpaca_configured, plan_rebalance


class _Resp:
    def __init__(self, payload, status=200):
        self.status_code = status
        self._p = payload
        self.content = json.dumps(payload).encode()
        self.text = json.dumps(payload)

    def json(self):
        return self._p


class _Session:
    def __init__(self):
        self.calls = []

    def request(self, method, url, headers=None, timeout=None, **kw):
        self.calls.append((method, url, headers, kw))
        return _Resp({"id": "o1", "status": "accepted"})


def test_not_configured_without_env(monkeypatch):
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)
    assert not alpaca_configured()
    with pytest.raises(AlpacaNotConfigured):
        AlpacaPaperClient()


def test_bracket_order_request_is_paper_only():
    s = _Session()
    c = AlpacaPaperClient("k", "s", session=s)
    c.submit_order("aapl", 3, "buy", limit_price=100.0, take_profit=110.0, stop_loss=95.0)
    method, url, headers, kw = s.calls[0]
    assert method == "POST" and url == f"{PAPER_BASE_URL}/v2/orders"
    assert headers["APCA-API-KEY-ID"] == "k"
    body = kw["json"]
    assert body["symbol"] == "AAPL" and body["qty"] == "3" and body["limit_price"] == "100.00"
    assert body["order_class"] == "bracket" and body["stop_loss"] == {"stop_price": "95.00"}
    with pytest.raises(ValueError):
        c.submit_order("AAPL", 0)


def test_http_error_raises():
    class Bad(_Session):
        def request(self, *a, **k):
            return _Resp({"message": "forbidden"}, 403)

    with pytest.raises(RuntimeError, match="403"):
        AlpacaPaperClient("k", "s", session=Bad()).account()


def test_plan_rebalance():
    picks = [{"ticker": "AAA", "weight": 0.1}, {"ticker": "BBB", "weight": 0.05}]
    orders = plan_rebalance(picks, 100_000, {"AAA": 100.0, "BBB": 50.0, "OLD": 20.0}, {"AAA": 40, "OLD": 30})
    assert {"symbol": "AAA", "side": "buy", "qty": 60, "ref_price": 100.0} in orders
    assert {"symbol": "BBB", "side": "buy", "qty": 100, "ref_price": 50.0} in orders
    assert {"symbol": "OLD", "side": "sell", "qty": 30, "ref_price": 20.0} in orders
