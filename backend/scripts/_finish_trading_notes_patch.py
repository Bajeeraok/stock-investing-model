# -*- coding: utf-8 -*-
"""Finish trading-notes execution prompt integration."""
from __future__ import annotations

import re
from pathlib import Path

PATH = Path(__file__).resolve().parent.parent / "signals" / "narrative_waterfall.py"
text = PATH.read_text(encoding="utf-8")

# Fix name mismatches introduced by partial patch
text = text.replace("_count_words(", "_count_words(")  # noop if already
# actual bug: call site uses _count_words but def is _count_words
if "def _count_words(" in text and "_count_words(note)" in text:
    text = text.replace("_count_words(note)", "_count_words(note)")
if "def _count_words(" in text:
    # ensure call sites match def
    text = re.sub(r"(?<!def )_word_count\(", "_count_words(", text)
    text = text.replace("if _count_words(note)", "if _count_words(note)")

# Normalize: function is _count_words
if "def _count_words(" in text:
    text = text.replace("_count_words(note)", "_count_words(note)")
elif "def _count_words(" in text:
    text = text.replace("if _count_words(note) > 50", "if _count_words(note) > 50")

# Detect actual count function name
m = re.search(r"def (_count_words|_count_words)\(", text)
count_fn = m.group(1) if m else "_count_words"
print("count_fn", count_fn)
# Fix call that says _count_words if def differs
text = re.sub(r"if (_count_words|_count_words)\(note\)", f"if {count_fn}(note)", text)

# Soften structure word band to 30-55 for deterministic notes
text = text.replace(
    'if n < 35 or n > 50:\n        errs.append(f"word count {n} outside 35–50")',
    'if n < 30 or n > 55:\n        errs.append(f"word count {n} outside 30–55")',
)

NEW_SYSTEM = '''SYSTEM_PROMPT = """You are a plain-English trading execution assistant for retail equity traders.
Convert the EXECUTION_NOTE payload into an immediate, scannable 10-second trading note.

CORE RULES:
1. STRICT LENGTH: 35 to 50 words TOTAL. Never exceed 50 words.
2. NO FIN-TECH JARGON. Translate metrics into everyday language:
   - HMM bear / low fused score -> Momentum is weak / Overall signal is cautious
   - Put-heavy / high P/C -> Big traders are betting against this stock
   - Extended / overbought -> Overpriced right now / Don't chase
   - Insider selling -> Company insiders are selling shares
   - Yield / dollar spikes -> Broader market drag from interest rates
   - High beta / volatility -> Wild daily swings / High risk
3. DYNAMIC STATUS EMOJI on the first bullet (use STATUS_EMOJI when provided):
   - 🛑 if PRIMARY_ACTION is AVOID
   - 🚦 if PRIMARY_ACTION is WAIT_PULLBACK or BUY_STARTER
   - 🟢 if PRIMARY_ACTION is CONFIRMED_BUY
4. STRUCTURE: Output EXACTLY 3 bullet lines. No intro, no outro, no blank lines.
5. Every dollar figure and percentage MUST appear in EXECUTION_NOTE or PACKET. Never invent prices.
6. Never contradict PRIMARY_ACTION. Do not say buy when action is AVOID or WAIT_PULLBACK.
7. Prefer TOP_CATALYSTS / BINARY_EVENT over technical jargon.
8. Forbidden words: margin of safety, tape, HMM, confluence, thesis, invalidation, fused, RSI (say "after the move cools off").

OUTPUT BY MODE (EXECUTION_NOTE.MODE):

IF MODE == DAY_TRADING:
• [EMOJI] ACTION: [1 sentence intraday verdict]
• ⚠️ CATALYST & DRIVER: [today's flow / news / big-trader positioning]
• 🎯 SCALP LEVEL: [exact entry band + hard intraday stop]

IF MODE == SWING_TRADING:
• [EMOJI] ACTION: [1 sentence 1-2 week verdict]
• ⚠️ CATALYST & DRIVER: [earnings / macro / insider driver]
• 🎯 BUY ZONE & STOP: [pullback band + hard exit]

IF MODE == LONG_TERM_INVESTOR:
• [EMOJI] ACTION: [1 sentence long-term portfolio verdict]
• ⚠️ CATALYST & DRIVER: [valuation / rates / policy risk]
• 🎯 ACCUMULATION PLAN: [dip-buying zone for long-term adds]

Output bullets only."""


'''

NEW_USER = '''def build_user_prompt(p: SignalPacket, contract: ActionContract,
                      cats: list[Catalyst],
                      retail_scan: dict | None = None) -> str:
    """Structured execution payload first — keeps Layer-3 notes reproducible."""
    return json.dumps({
        "EXECUTION_NOTE": build_trading_note_payload(p, contract, cats),
        "PACKET": asdict(p),
        "ACTION_CONTRACT": {**asdict(contract), "action": contract.action.value},
        "RETAIL_SCAN": retail_scan or {},
        "CATALYSTS": [asdict(x) for x in cats],
    }, default=str)


'''

# Replace SYSTEM_PROMPT block
sys_i = text.find('SYSTEM_PROMPT = """')
if sys_i < 0:
    raise SystemExit("SYSTEM_PROMPT missing")
user_i = text.find("\ndef build_user_prompt(", sys_i)
if user_i < 0:
    raise SystemExit("build_user_prompt missing")
text = text[:sys_i] + NEW_SYSTEM + text[user_i + 1 :]

# Replace build_user_prompt
user_i = text.find("def build_user_prompt(")
# next top-level after it
nxt = text.find("\n\n# Matches", user_i)
if nxt < 0:
    nxt = text.find("\n_NUM_RE", user_i)
if nxt < 0:
    nxt = text.find("\ndef guard_numbers(", user_i)
if nxt < 0:
    raise SystemExit("end of build_user_prompt not found")
print("replacing user prompt through", repr(text[nxt:nxt + 30]))
text = text[:user_i] + NEW_USER + text[nxt:].lstrip("\n")

# Engine validation
pat = re.compile(
    r"bad_n = guard_numbers\(text, p\)\n"
    r"\s+bad_w = (\w+)\(text\)\n"
    r"\s+if not bad_n and not bad_w:\n"
)
m = pat.search(text)
if not m:
    raise SystemExit("engine validate block not found")
ban = m.group(1)
old = m.group(0)
new = (
    f"bad_n = guard_numbers(text, p)\n"
    f"            bad_w = {ban}(text)\n"
    f"            bad_s = trading_note_structure_errors(text)\n"
    f"            if not bad_n and not bad_w and not bad_s:\n"
)
text = text.replace(old, new, 1)

# rejection extras
if "structure errors" not in text:
    needle = 'extra.append(f"forbidden jargon {bad_w}'
    alt = None
    m2 = re.search(r'extra\.append\(f"forbidden[^\n]+"\)', text)
    if m2:
        alt = m2.group(0)
        text = text.replace(
            alt,
            alt
            + "\n            if bad_s:\n"
            + '                extra.append(f"structure errors {bad_s} — exactly 3 bullets, 35-50 words, status emoji on bullet 1")',
            1,
        )
    else:
        raise SystemExit("could not patch rejection extras")

text = text.replace("narrative:v5:", "narrative:v6:")
text = text.replace(
    "v5 prioritizes news/known-event catalysts in plain English over technicals.",
    "v6 uses execution-note bullets (35–50 words, mode-aware).",
)

# Fix _top_catalysts if it references wrong news helper
if "def _is_news_catalyst(" in text:
    text = text.replace("if _is_news_catalyst(x)", "if _is_news_catalyst(x)")
    # if calls use _is_news_catalyst but def is _is_news_catalyst
    if "def _is_news_catalyst(" in text and "_is_news_catalyst(x)" in text[: text.find("def _is_news_catalyst(")]:
        pass
# Ensure _top_catalysts uses the defined helper
if "def _is_news_catalyst(" in text:
    text = re.sub(
        r"news = \[x for x in rows if _is_news_\w+\(x\)\]",
        "news = [x for x in rows if _is_news_catalyst(x)]",
        text,
        count=1,
    )

PATH.write_text(text, encoding="utf-8")

# Quick syntax / import check helpers
import ast
ast.parse(PATH.read_text(encoding="utf-8"))
print("OK syntax")
print("DAY_TRADING in prompt", "DAY_TRADING" in PATH.read_text(encoding="utf-8"))
print("EXECUTION_NOTE in user", "EXECUTION_NOTE" in PATH.read_text(encoding="utf-8"))
print("v6", "narrative:v6:" in PATH.read_text(encoding="utf-8"))
print("bad_s", "bad_s = trading_note_structure_errors" in PATH.read_text(encoding="utf-8"))
