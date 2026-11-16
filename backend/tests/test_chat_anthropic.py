import sys
import types

from api.routers import chat


def test_chat_uses_anthropic_key(monkeypatch):
    seen = {}

    class _Msgs:
        def create(self, **kw):
            seen.update(kw)
            return types.SimpleNamespace(content=[types.SimpleNamespace(type="text", text="NVDA is locked by Trend weather.")])

    class _Client:
        def __init__(self, api_key):
            seen["key"] = api_key
            self.messages = _Msgs()

    monkeypatch.setitem(sys.modules, "anthropic", types.SimpleNamespace(Anthropic=_Client))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(chat, "_anthropic_client", None)
    out = chat._call_llm("Why is NVDA locked?", "NVDA: entry_mode=hard_lock")
    assert out == "NVDA is locked by Trend weather."
    assert seen["key"] == "test-key"
    assert "NVDA: entry_mode=hard_lock" in seen["system"]
    assert seen["messages"] == [{"role": "user", "content": "Why is NVDA locked?"}]
