"""
Chat copilot: answers questions using your model data + LLM.
Uses dashboard context (passed by client or loaded from last_run).
"""
from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger("api.chat")

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(ROOT))

from config_loader import load_config
from scripts.run_daily import load_last_run

router = APIRouter()

_openai_client = None
_openai_client_key: str | None = None
_openai_lock = threading.Lock()

SYSTEM_PROMPT = """You are a copilot for a stock investing model. You answer questions using ONLY the provided data.

RULES:
- Base answers strictly on the context data below. Do not invent numbers or tickers.
- If the user asks about a ticker not in the data, say it's not in the current watchlist/portfolio.
- Explain model outputs in plain English using the decision fields provided:
  gates (what blocks the entry), entry_mode (full_go/starter_only/hard_lock),
  entry bands (price zones to buy into), dip_zone (score-30-50 dip cohort),
  unlock_sequence (what has to happen before buying), R:R, and vs-FV%.
- For "should I buy / is this a good entry" questions, lead with entry_mode +
  the specific gate blocking + the band range — never generic advice.
- Keep answers concise (2-4 sentences unless summarizing many items).
- Never recommend buying or selling; only explain what the model shows.
- When comparing, cite specific values from the data.

Context data (from the user's dashboard):"""


def _build_context(dashboard_snapshot: dict | None) -> str:
    """Build context string from dashboard snapshot or last_run."""
    if dashboard_snapshot and isinstance(dashboard_snapshot, dict):
        # Client sent current dashboard - use it
        parts = []
        if dashboard_snapshot.get("signals"):
            rows = []
            for s in dashboard_snapshot["signals"][:30]:
                t = s.get("ticker", "")
                score = s.get("composite_buy")
                regime = s.get("regime", "")
                sig = s.get("signal", "")
                sugg = s.get("short_suggestion", "")
                rsi = s.get("rsi")
                # Decision fields — this is what the LLM needs to actually
                # explain the signal, not just parrot the score back.
                em = s.get("entry_mode") or ""
                gp = s.get("gates_passed")
                gt = s.get("gates_total")
                st_band = s.get("st_band") or {}
                band_txt = ""
                if st_band.get("low") is not None and st_band.get("high") is not None:
                    band_txt = f" st_band=${st_band['low']:.0f}–${st_band['high']:.0f}"
                unlock = s.get("unlock_sequence") or s.get("unlock_summary") or ""
                dip = " dip_zone" if s.get("dip_zone") else ""
                gate_txt = f" gates={gp}/{gt}" if gp is not None and gt is not None else ""
                em_txt = f" entry_mode={em}" if em else ""
                un_txt = f" unlock={unlock[:80]}" if unlock else ""
                rows.append(
                    f"  {t}: score={score} regime={regime} signal={sig} RSI={rsi} suggestion={sugg}"
                    f"{em_txt}{gate_txt}{band_txt}{dip}{un_txt}"
                )
            parts.append("Signals:\n" + "\n".join(rows))
        if dashboard_snapshot.get("portfolio", {}).get("per_holding"):
            rows = []
            for h in dashboard_snapshot["portfolio"]["per_holding"][:20]:
                t = h.get("ticker", "")
                val = h.get("value")
                pct = h.get("pct")
                score = h.get("score")
                regime = h.get("regime", "")
                rows.append(f"  {t}: value=${val} pct={pct}% score={score} regime={regime}")
            parts.append("Portfolio:\n" + "\n".join(rows))
        if dashboard_snapshot.get("what_changed"):
            rows = []
            for w in dashboard_snapshot["what_changed"][:15]:
                t = w.get("ticker", "")
                summary = w.get("summary") or ", ".join(w.get("changes", [])[:3])
                rows.append(f"  {t}: {summary}")
            parts.append("What changed:\n" + "\n".join(rows))
        if dashboard_snapshot.get("opportunities"):
            rows = [f"  {o.get('ticker')}: score={o.get('composite_buy')} regime={o.get('regime')} - {o.get('reason', '')}" for o in dashboard_snapshot["opportunities"][:10]]
            parts.append("Opportunities:\n" + "\n".join(rows))
        cfg = dashboard_snapshot.get("config", {})
        parts.append(f"Config: buy_min={cfg.get('score', {}).get('buy_min', 70)} sell_max={cfg.get('score', {}).get('sell_max', 30)}")
        return "\n\n".join(parts)

    # Fallback: last_run from disk
    last = load_last_run()
    if not last:
        return "No saved run data. Run the daily pipeline (run_daily.py) or refresh the dashboard first."
    config = load_config()
    rows = []
    for ticker, r in list(last.items())[:40]:
        score = r.get("composite_buy")
        regime = r.get("regime", "")
        rows.append(f"  {ticker}: score={score} regime={regime}")
    cfg = config.get("score", {})
    return f"Last run signals:\n" + "\n".join(rows) + f"\n\nConfig: buy_min={cfg.get('buy_min', 70)} sell_max={cfg.get('sell_max', 30)}"


_anthropic_client = None
_anthropic_client_key: str | None = None


def _call_anthropic(api_key: str, question: str, full_context: str) -> str:
    import anthropic

    global _anthropic_client, _anthropic_client_key
    with _openai_lock:
        if _anthropic_client is None or _anthropic_client_key != api_key:
            _anthropic_client = anthropic.Anthropic(api_key=api_key)
            _anthropic_client_key = api_key
        client = _anthropic_client
    msg = client.messages.create(
        model=os.getenv("ANTHROPIC_CHAT_MODEL", "claude-haiku-4-5-20251001"),
        max_tokens=500,
        system=full_context,
        messages=[{"role": "user", "content": question}],
    )
    return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()


def _call_llm(question: str, context: str) -> str:
    """Anthropic (same key as the ticker Why section), falling back to OpenAI if only that key is set."""
    data_cfg = load_config().get("data", {})
    full_context = f"{SYSTEM_PROMPT}\n\n```\n{context}\n```"
    anthropic_key = os.getenv("ANTHROPIC_API_KEY") or data_cfg.get("anthropic_api_key")
    if anthropic_key:
        return _call_anthropic(anthropic_key, question, full_context)

    api_key = os.getenv("OPENAI_API_KEY") or data_cfg.get("openai_api_key")
    if not api_key:
        return (
            "Chat requires an Anthropic API key. Set ANTHROPIC_API_KEY in the environment or "
            "add data.anthropic_api_key to config.yaml. This copilot explains your model's outputs using your data."
        )

    try:
        from openai import OpenAI
    except ImportError:
        return "Install openai: pip install openai"

    global _openai_client, _openai_client_key
    with _openai_lock:
        if _openai_client is None or _openai_client_key != api_key:
            _openai_client = OpenAI(api_key=api_key)
            _openai_client_key = api_key
        client = _openai_client
    resp = client.chat.completions.create(
        model=os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini"),
        messages=[{"role": "system", "content": full_context}, {"role": "user", "content": question}],
        max_tokens=500,
        temperature=0.3,
    )
    return (resp.choices[0].message.content or "").strip()


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    context: dict | None = Field(None, description="Optional dashboard snapshot for fresher context")


class ChatResponse(BaseModel):
    answer: str
    sources: list[str] = Field(default_factory=list)


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Answer a question using model data + LLM. Pass context from dashboard for live data."""
    try:
        context_str = _build_context(request.context)
        answer = _call_llm(request.question.strip(), context_str)
        sources = []
        if request.context:
            sources.append("Dashboard (current)")
        else:
            sources.append("Last run (saved)")
        return ChatResponse(answer=answer, sources=sources)
    except Exception as e:
        logger.exception("Chat error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
