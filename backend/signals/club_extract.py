"""
Structured extraction for clipped CNBC Investing Club articles (personal subscription, clipped
manually via the bookmarklet in docs/operations/ARTICLE_CLIPPER_BOOKMARKLET.md).

Claude (Haiku) turns long-form article text into a small per-ticker record: Club rating,
price target, any trade the Club made, stance, thesis and risks. Only these fields and a short
summary are kept, not the article text. Advisory only: shown as a second opinion and scored by
forward tracking; never changes our bands, gates or scores.
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Callable

logger = logging.getLogger(__name__)

LLMFn = Callable[[str, str], str]
MAX_TICKERS = 12
MAX_INPUT_CHARS = 18_000
_ACTIONS = {"bought", "initiated", "sold", "trimmed", "exited"}
_STANCES = {"bullish", "neutral", "bearish"}

SYSTEM = (
    "You extract facts from a CNBC Investing Club article for a private investing notebook. "
    "Return ONLY a JSON object, no prose. Use null when the article does not state a value; never guess. "
    'Shape: {"summary": str (<=2 sentences, plain English), "tickers": {"SYM": {'
    '"rating": 1|2|3|null (the Club\'s own rating: 1 buy now, 2 wait for a pullback, 3 hold/don\'t buy), '
    '"price_target": number|null (the Club\'s price target, not Wall Street\'s), '
    '"action": "bought"|"initiated"|"sold"|"trimmed"|"exited"|null (a trade the Club made in this article), '
    '"shares": integer|null, "trade_price": number|null, '
    '"stance": "bullish"|"neutral"|"bearish", '
    '"thesis": [str] (<=3 short reasons the Club gives), "risks": [str] (<=2)}}}. '
    "Include only tickers the article actually discusses, uppercase US symbols."
)

_PAREN_TICKER = re.compile(r"\((?:NASDAQ|NYSE|NYSEARCA|NYSEAMERICAN|AMEX|CBOE)?:?\s*([A-Z]{1,5}(?:[.-][A-Z])?)\)")
_NOT_TICKERS = {"AI", "CEO", "CFO", "EPS", "GDP", "FDA", "SEC", "ETF", "IPO", "US", "USA", "EU", "UK", "PT", "Q1", "Q2", "Q3", "Q4", "YOY", "CPI", "FED"}


def llm_configured() -> bool:
    return bool((os.getenv("ANTHROPIC_API_KEY") or "").strip())


def make_llm(model: str = "claude-haiku-4-5-20251001", max_tokens: int = 1500) -> LLMFn:
    import anthropic

    client = anthropic.Anthropic()

    def call(system: str, user: str) -> str:
        msg = client.messages.create(
            model=model, max_tokens=max_tokens, system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(b.text for b in msg.content if b.type == "text")

    return call


def detect_tickers(text: str, hints: list[str] | None = None) -> list[str]:
    """Bookmarklet hints (CNBC quote links in the article) first, then '(NASDAQ:AAPL)'-style mentions."""
    out: list[str] = []
    for raw in list(hints or []) + _PAREN_TICKER.findall(text or ""):
        sym = str(raw or "").strip().upper().replace(".", "-")
        if sym and sym not in _NOT_TICKERS and re.fullmatch(r"[A-Z]{1,5}(-[A-Z])?", sym) and sym not in out:
            out.append(sym)
    return out[:MAX_TICKERS]


def _num(v: Any) -> float | None:
    try:
        x = float(str(v).replace("$", "").replace(",", ""))
        return round(x, 2) if x > 0 else None
    except (TypeError, ValueError):
        return None


def _strs(v: Any, n: int) -> list[str]:
    if not isinstance(v, list):
        return []
    return [str(s).strip()[:200] for s in v if str(s).strip()][:n]


def _clean_entry(e: Any) -> dict[str, Any] | None:
    if not isinstance(e, dict):
        return None
    rating = e.get("rating")
    rating = int(rating) if str(rating) in ("1", "2", "3") else None
    action = str(e.get("action") or "").lower() or None
    action = action if action in _ACTIONS else None
    stance = str(e.get("stance") or "").lower()
    shares = _num(e.get("shares"))
    return {
        "rating": rating,
        "price_target": _num(e.get("price_target")),
        "action": action,
        "shares": int(shares) if shares else None,
        "trade_price": _num(e.get("trade_price")),
        "stance": stance if stance in _STANCES else "neutral",
        "thesis": _strs(e.get("thesis"), 3),
        "risks": _strs(e.get("risks"), 2),
    }


def parse_extraction(raw: str) -> dict[str, Any] | None:
    if not raw:
        return None
    i, j = raw.find("{"), raw.rfind("}")
    if i < 0 or j <= i:
        return None
    try:
        data = json.loads(raw[i : j + 1])
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    tickers: dict[str, Any] = {}
    for sym, e in (data.get("tickers") or {}).items() if isinstance(data.get("tickers"), dict) else []:
        s = str(sym).strip().upper().replace(".", "-")
        ce = _clean_entry(e)
        if ce and re.fullmatch(r"[A-Z]{1,5}(-[A-Z])?", s):
            tickers[s] = ce
    return {"summary": str(data.get("summary") or "").strip()[:400], "tickers": dict(list(tickers.items())[:MAX_TICKERS])}


def extract_club_view(
    title: str,
    text: str,
    *,
    hints: list[str] | None = None,
    llm: LLMFn | None = None,
) -> dict[str, Any] | None:
    """{summary, tickers: {SYM: fields}} or None when no LLM is configured or the call fails."""
    if llm is None:
        if not llm_configured():
            return None
        try:
            llm = make_llm()
        except Exception as e:
            logger.warning("club_extract: anthropic unavailable: %s", e)
            return None
    found = detect_tickers(text, hints)
    user = (
        f"Title: {title}\n"
        + (f"Tickers linked in the article: {', '.join(found)}\n" if found else "")
        + f"\nArticle:\n{(text or '')[:MAX_INPUT_CHARS]}"
    )
    try:
        return parse_extraction(llm(SYSTEM, user))
    except Exception as e:
        logger.warning("club_extract failed: %s", e)
        return None


def club_label(view: dict[str, Any]) -> tuple[str, str]:
    """(label, bias) for the Second opinions row. Labels feed bias_from_label in forward tracking."""
    action, rating = view.get("action"), view.get("rating")
    if action in ("sold", "trimmed", "exited"):
        return ("Trim", "bearish")
    if rating == 1 or action in ("bought", "initiated"):
        return ("Buy", "bullish")
    if rating == 2:
        return ("Wait for pullback", "neutral")
    if rating == 3:
        return ("Don't buy", "neutral")
    return ({"bullish": "Positive view", "bearish": "Negative view"}.get(view.get("stance") or "", "Neutral view"), "neutral")
