"""On-view LLM wrap for Phase-1 catalyst cards.

Advisory only — never mutates bands, gates, MOS, HMM, or scores.
Number-guarded against the user prompt (packet facts + source cards).
Cached on ticker + mode + asof + headline hash (Redis when available).
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Optional

from signals.narrative_waterfall import (
    LLMFn,
    SignalPacket,
    _NUM_RE,
    derive_action_contract,
    load_allowlist,
)

logger = logging.getLogger("signals.catalyst_llm_wrap")

SYSTEM_PROMPT = """You write short retail trading notes from classified headlines.
Advisory only — you do not change price bands, gates, MOS, HMM, scores, or the action contract.

HARD RULES:
1. Every dollar figure and percentage you write MUST appear verbatim in SOURCE or PACKET. Never invent a price, level, or probability.
2. Do not use BUY/SELL/ADD/TRIM except if those exact words appear in PACKET.
3. Keep each card's event_type and direction unchanged. Do not add new catalysts.
4. Output ONLY JSON (no markdown fences): {"cards":[{"event_type":"...","wrap":"1-2 sentences","watch":"optional one clause"}]}
5. wrap explains what the headline means for THIS ticker's existing plan using PACKET levels when they appear in PACKET. If a number is not in SOURCE or PACKET, speak qualitatively.
6. Tone: measured. No hype, no certainty language.
7. End implicit stance: the note does not change bands or gates."""

_CACHE_TTL_SECONDS = 2 * 24 * 3600  # 2 days; headline hash already busts on news change


def catalyst_headline_hash(cards: list[dict[str, Any]] | None) -> str:
    payload = [
        {
            "event_type": c.get("event_type"),
            "title": c.get("mechanism") or c.get("title") or "",
            "count": int(c.get("headline_count") or 1),
        }
        for c in (cards or [])
        if isinstance(c, dict)
    ]
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def numbers_from_blob(obj: Any) -> set[float]:
    """Numbers the model was shown — the only values a wrap may cite."""
    out: set[float] = set()

    def add_from_text(text: str) -> None:
        for m in _NUM_RE.finditer(text):
            raw = (m.group(1) or m.group(2) or m.group(3) or "").replace(",", "")
            if not raw:
                continue
            try:
                v = abs(float(raw))
            except ValueError:
                continue
            out.add(round(v, 2))
            out.add(round(v))

    def walk(x: Any) -> None:
        if isinstance(x, bool):
            return
        if isinstance(x, (int, float)):
            v = abs(float(x))
            out.add(round(v, 2))
            out.add(round(v))
        elif isinstance(x, str):
            add_from_text(x)
        elif isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, (list, tuple)):
            for v in x:
                walk(v)

    walk(obj)
    return out


def guard_text(text: str, allowed: set[float]) -> list[str]:
    bad: list[str] = []
    for m in _NUM_RE.finditer(text or ""):
        raw = (m.group(1) or m.group(2) or m.group(3) or "").replace(",", "")
        if not raw:
            continue
        try:
            v = round(float(raw), 2)
        except ValueError:
            continue
        if v not in allowed and round(v) not in allowed:
            bad.append(m.group(0))
    return bad


def packet_facts(packet: SignalPacket | None) -> dict[str, Any]:
    if packet is None:
        return {}
    entry = None
    if packet.entry_band is not None:
        entry = packet.entry_band.fmt()
    action = None
    try:
        if not packet.validate():
            action = derive_action_contract(packet).action.value
    except Exception:
        action = None
    return {
        "ticker": packet.ticker,
        "mode": packet.mode,
        "asof": packet.asof,
        "spot": packet.spot,
        "verdict": packet.verdict,
        "action": action,
        "entry_band": entry,
        "stop": packet.stop,
        "invalidation": packet.invalidation,
        "target": packet.target,
        "rsi": packet.rsi,
        "hmm_bull_pct": packet.hmm_bull_pct,
        "fused_confidence_pct": packet.fused_confidence_pct,
    }


def _source_cards(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for c in cards:
        if not isinstance(c, dict):
            continue
        out.append({
            "event_type": c.get("event_type"),
            "name": c.get("name"),
            "direction": c.get("direction"),
            "mechanism": c.get("mechanism"),
            "watch": c.get("watch"),
            "horizon": c.get("horizon"),
            "headline_count": c.get("headline_count"),
            "age_label": c.get("age_label"),
        })
    return out


def _parse_wrap_json(text: str) -> dict[str, Any] | None:
    s = (text or "").strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[-1]
        if s.rstrip().endswith("```"):
            s = s.rstrip()[:-3]
    i, j = s.find("{"), s.rfind("}")
    if i < 0 or j <= i:
        return None
    try:
        obj = json.loads(s[i : j + 1])
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def _rebuild_draft(card: dict[str, Any], ticker: str) -> str:
    sym = (ticker or "").strip().upper()
    body = card.get("wrap") or card.get("mechanism") or ""
    bits = [f"{sym} · {card.get('name') or card.get('event_type')} ({card.get('direction')}) — {body}"]
    meta = " · ".join(x for x in (card.get("source") or "", card.get("age_label") or "") if x)
    if meta:
        bits.append(meta)
    bits.append("Advisory only — does not change bands or gates.")
    return " ".join(str(b) for b in bits)[:500]


def apply_wraps(
    cards: list[dict[str, Any]],
    wraps_by_type: dict[str, dict[str, str]],
    *,
    ticker: str,
    allowed: set[float] | None,
) -> list[dict[str, Any]]:
    """Merge guarded wraps onto Phase-1 cards. Unknown types and bad numbers are dropped."""
    out: list[dict[str, Any]] = []
    for c in cards:
        row = dict(c)
        et = str(c.get("event_type") or "")
        w = wraps_by_type.get(et) or {}
        wrap = (w.get("wrap") or "").strip()
        watch = (w.get("watch") or "").strip()
        wrap_ok = bool(wrap) and (allowed is None or not guard_text(wrap, allowed))
        watch_ok = bool(watch) and (allowed is None or not guard_text(watch, allowed))
        if wrap_ok:
            row["wrap"] = wrap
            row["draft_note"] = _rebuild_draft(row, ticker)
        if watch_ok:
            row["watch"] = watch
        out.append(row)
    return out


class CatalystWrapEngine:
    def __init__(self, llm: Optional[LLMFn] = None, max_retries: int = 2):
        self.llm = llm
        self.max_retries = max_retries
        self._mem_cache: dict[str, str] = {}

    def _cache_get(self, key: str) -> Optional[str]:
        try:
            from signals.cache import get_cached
            val = get_cached(key, as_json=False)
            if val is not None:
                return val
        except Exception:
            pass
        return self._mem_cache.get(key)

    def _cache_set(self, key: str, value: str) -> None:
        self._mem_cache[key] = value
        try:
            from signals.cache import set_cached
            set_cached(key, value, _CACHE_TTL_SECONDS)
        except Exception:
            pass

    def generate(
        self,
        cards: list[dict[str, Any]],
        *,
        ticker: str,
        asof: str,
        mode: str,
        packet: SignalPacket | None,
    ) -> tuple[dict[str, dict[str, str]], str]:
        """Returns (wraps_by_event_type, status). status ∈ ok|cached|skipped|fallback."""
        if self.llm is None or not cards:
            return {}, "skipped"
        h = catalyst_headline_hash(cards)
        key = f"catalyst_wrap:{ticker}:{mode}:{asof}:{h}"
        cached = self._cache_get(key)
        if cached is not None:
            try:
                parsed = json.loads(cached)
                if isinstance(parsed, dict):
                    return {str(k): v for k, v in parsed.items() if isinstance(v, dict)}, "cached"
            except json.JSONDecodeError:
                pass

        facts = packet_facts(packet)
        source = _source_cards(cards)
        user_obj = {"PACKET": facts, "SOURCE": source}
        user = json.dumps(user_obj, default=str)
        allowed = numbers_from_blob(user_obj)

        prompt = user
        last_good: dict[str, dict[str, str]] = {}
        allowed_types = {str(c.get("event_type")) for c in cards}
        for attempt in range(self.max_retries + 1):
            try:
                text = self.llm(SYSTEM_PROMPT, prompt).strip()
            except Exception as exc:
                logger.warning("[catalyst_wrap] LLM call failed for %s: %s", ticker, exc)
                return last_good, ("ok" if last_good else "fallback")
            obj = _parse_wrap_json(text)
            rows = (obj or {}).get("cards") if obj else None
            if not isinstance(rows, list):
                prompt = user + f"\n\nREJECTED attempt {attempt + 1}: output valid JSON with a cards array."
                continue
            wraps: dict[str, dict[str, str]] = {}
            bad_all: list[str] = []
            for row in rows:
                if not isinstance(row, dict):
                    continue
                et = str(row.get("event_type") or "")
                if et not in allowed_types:
                    continue
                wrap = str(row.get("wrap") or "").strip()
                watch = str(row.get("watch") or "").strip()
                bad = guard_text(wrap, allowed) + (guard_text(watch, allowed) if watch else [])
                if bad:
                    bad_all.extend(bad)
                    continue
                if wrap:
                    wraps[et] = {"wrap": wrap, "watch": watch}
            if wraps:
                last_good = wraps
            if wraps and not bad_all:
                if len(wraps) >= len(allowed_types):
                    self._cache_set(key, json.dumps(wraps))
                return wraps, "ok"
            prompt = (
                user
                + f"\n\nREJECTED attempt {attempt + 1}: invented or missing numbers {bad_all}. "
                "Rewrite using only SOURCE/PACKET numbers."
            )
        if last_good:
            return last_good, "ok"
        return {}, "fallback"


_ENGINE: Optional[CatalystWrapEngine] = None


def wrap_catalyst_cards(
    cards: list[dict[str, Any]] | None,
    *,
    ticker: str,
    asof: str,
    mode: str = "scout",
    packet: SignalPacket | None = None,
    llm: Optional[LLMFn] = None,
    engine: Optional[CatalystWrapEngine] = None,
    on_view: bool = True,
) -> dict[str, Any]:
    """Phase-1 cards in, same cards out plus optional guarded `wrap`.

    LLM runs only on page view (or allowlisted tickers). Cache key is
    ticker+mode+asof+headline hash so a new cluster regenerates and a spot
    tick does not.
    """
    src = [dict(c) for c in (cards or []) if isinstance(c, dict)]
    h = catalyst_headline_hash(src)
    allow = load_allowlist()
    use_llm = llm if (on_view or ticker.upper() in allow) else None

    global _ENGINE
    if engine is None:
        if _ENGINE is None or _ENGINE.llm is not use_llm:
            _ENGINE = CatalystWrapEngine(use_llm)
        engine = _ENGINE

    wraps, status = engine.generate(
        src, ticker=ticker.upper().strip(), asof=asof, mode=mode, packet=packet,
    )
    allowed = None if status == "cached" else numbers_from_blob(
        {"PACKET": packet_facts(packet), "SOURCE": _source_cards(src)}
    )
    merged = apply_wraps(src, wraps, ticker=ticker, allowed=allowed)
    return {
        "status": "ok",
        "ticker": ticker.upper().strip(),
        "mode": mode,
        "asof": asof,
        "headline_hash": h,
        "wrap_status": status,
        "cards": merged,
    }
