from __future__ import annotations

import json

from signals.club_extract import club_label, detect_tickers, extract_club_view, parse_extraction


def _fake_llm(payload):
    return lambda system, user: "Here you go:\n" + json.dumps(payload)


def test_detect_tickers_hints_and_parens():
    text = "We like Apple (NASDAQ:AAPL) and Nvidia (NVDA). AI (AI) is hot; the CEO said so."
    assert detect_tickers(text, ["amzn"]) == ["AMZN", "AAPL", "NVDA"]


def test_parse_cleans_fields():
    raw = json.dumps({"summary": "S", "tickers": {"aapl": {
        "rating": "1", "price_target": "$250", "action": "Bought", "shares": 50, "trade_price": 231.5,
        "stance": "BULLISH", "thesis": ["a", "b", "c", "d"], "risks": ["r"]}, "bad sym": {}}})
    out = parse_extraction(raw)
    v = out["tickers"]["AAPL"]
    assert v["rating"] == 1 and v["price_target"] == 250 and v["action"] == "bought"
    assert v["stance"] == "bullish" and len(v["thesis"]) == 3 and "BAD SYM" not in out["tickers"]
    assert parse_extraction("no json") is None


def test_extract_without_key_returns_none(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert extract_club_view("t", "body") is None


def test_extract_with_fake_llm():
    out = extract_club_view("t", "body", llm=_fake_llm({"summary": "x", "tickers": {"MSFT": {"rating": 2}}}))
    assert out["tickers"]["MSFT"]["rating"] == 2


def test_club_label_mapping():
    assert club_label({"action": "trimmed", "rating": 1}) == ("Trim", "bearish")
    assert club_label({"rating": 1}) == ("Buy", "bullish")
    assert club_label({"rating": 2}) == ("Wait for pullback", "neutral")
    assert club_label({"rating": 3}) == ("Don't buy", "neutral")
    assert club_label({"stance": "bullish"})[1] == "neutral"


def test_club_view_flows_to_cards_and_second_opinions(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    from signals import manual_catalysts as mc
    from signals.second_opinions import club_opinion

    club = {"rating": 1, "price_target": 250.0, "action": "bought", "shares": 50, "trade_price": 231.5,
            "stance": "bullish", "thesis": ["Cloud growth"], "risks": ["Capex"]}
    mc.add_manual_article("AAPL", title="Club buys Apple", text="long body", url="https://cnbc.com/x", club=club, summary="We bought.")
    row = mc._load()["AAPL"][0]
    assert row["text"] == "We bought." and "long body" not in json.dumps(row)
    card = mc.manual_cards_for_ticker("AAPL")[0]
    assert card["name"] == "CNBC Investing Club" and "PT $250.00" in card["mechanism"]
    op = club_opinion("AAPL")
    assert op["label"] == "Buy" and op["bias"] == "bullish" and "PT $250" in op["detail"]
    assert club_opinion("MSFT") is None


def test_ingest_stores_each_detected_ticker(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    monkeypatch.delenv("ARTICLE_INGEST_SECRET", raising=False)
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import signals.club_extract as ce
    from api.routers.article_ingest import router
    from signals import manual_catalysts as mc

    monkeypatch.setattr(ce, "llm_configured", lambda: True)
    monkeypatch.setattr(ce, "make_llm", lambda: _fake_llm({"summary": "s", "tickers": {"NVDA": {"rating": 1}}}))
    app = FastAPI()
    app.include_router(router)
    res = TestClient(app).post(
        "/ingest/article",
        content=json.dumps({"ticker": "", "tickers": ["NVDA", "AMD"], "title": "Club update", "text": "body"}),
        headers={"Content-Type": "text/plain"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["tickers"] == ["NVDA", "AMD"]
    assert mc._load()["NVDA"][0]["club"]["rating"] == 1
    assert "club" not in mc._load()["AMD"][0]
