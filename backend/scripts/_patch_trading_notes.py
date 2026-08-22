# -*- coding: utf-8 -*-
"""Patch narrative_waterfall.py for execution-style trading notes."""
from __future__ import annotations

from pathlib import Path

PATH = Path(__file__).resolve().parent.parent / "signals" / "narrative_waterfall.py"
text = PATH.read_text(encoding="utf-8")

HELPERS = r'''
# ── Execution-note payload (LLM + deterministic share this contract) ──

_MODE_TO_EXEC = {
    "scout": "DAY_TRADING",
    "swing": "SWING_TRADING",
    "owner": "LONG_TERM_INVESTOR",
}

_PRIMARY_ACTION_EMOJI = {
    "AVOID": "🛑",
    "WAIT_PULLBACK": "🚦",
    "BUY_STARTER": "🚦",
    "CONFIRMED_BUY": "🟢",
}


def map_execution_mode(mode: str) -> str:
    return _MODE_TO_EXEC.get((mode or "").strip().lower(), "SWING_TRADING")


def map_primary_action(c: ActionContract) -> str:
    if c.action is Action.STAND_ASIDE:
        return "AVOID"
    if c.action is Action.BUY:
        return "CONFIRMED_BUY"
    if c.action in (Action.STARTER_BUY, Action.PLACE_LIMIT):
        return "BUY_STARTER"
    return "WAIT_PULLBACK"


def primary_action_emoji(primary: str) -> str:
    return _PRIMARY_ACTION_EMOJI.get(primary, "🚦")


def _plain_catalyst_text(x: "Catalyst") -> str:
    """Strip News:/Known event: prefixes and fin-tech jargon for retail bullets."""
    mech = (x.mechanism or x.name or "").strip()
    for prefix in ("News:", "Known event:", "Known Event:"):
        if mech.startswith(prefix):
            mech = mech[len(prefix):].strip()
    low = mech.lower()
    replacements = (
        ("hmm bear", "momentum is weak"),
        ("hmm bull", "momentum is firm"),
        ("put-heavy", "big traders are betting against this stock"),
        ("high p/c", "big traders are betting against this stock"),
        ("overbought", "overpriced right now — don't chase"),
        ("insider selling", "company insiders are selling shares"),
        ("margin of safety", "discount to fair value"),
    )
    out = mech
    for a, b in replacements:
        if a in low:
            out = re.sub(re.escape(a), b, out, flags=re.IGNORECASE)
    return out.rstrip(".")


def _top_catalysts(cats: list["Catalyst"] | None) -> list[str]:
    rows = list(cats or [])
    news = [x for x in rows if _is_news_catalyst(x)]
    ordered = news + [x for x in rows if x not in news]
    out: list[str] = []
    for x in ordered:
        t = _plain_catalyst_text(x)
        if t and t not in out:
            out.append(t)
        if len(out) >= 2:
            break
    if not out:
        out = ["No fresh company catalyst in the packet"]
    return out


def _binary_event_label(cats: list["Catalyst"] | None) -> str:
    for x in cats or []:
        blob = f"{x.name or ''} {x.mechanism or ''}"
        m = re.search(r"in\s+(\d+)\s+days?", blob, flags=re.IGNORECASE)
        if m:
            name = (x.name or "Event").split("(")[0].strip() or "Event"
            return f"{name} in {m.group(1)} days"
    return "NONE"


def _buy_zone_label(p: SignalPacket) -> str:
    if p.entry_band:
        return p.entry_band.fmt()
    return "n/a"


def _stop_label(p: SignalPacket) -> str:
    walk = p.stop if p.stop is not None else p.invalidation
    if walk is None:
        return "n/a"
    if p.spot and float(p.spot) > 0:
        pct = (float(walk) - float(p.spot)) / float(p.spot) * 100.0
        return f"{pct:.1f}% (${walk:,.2f})"
    return f"${walk:,.2f}"


def build_trading_note_payload(
    p: SignalPacket,
    c: ActionContract,
    cats: list["Catalyst"] | None = None,
) -> dict:
    """Deterministic JSON fed to the LLM — keeps notes reproducible."""
    primary = map_primary_action(c)
    return {
        "MODE": map_execution_mode(p.mode),
        "TICKER": (p.ticker or "").upper(),
        "PRIMARY_ACTION": primary,
        "STATUS_EMOJI": primary_action_emoji(primary),
        "TOP_CATALYSTS": _top_catalysts(cats),
        "BUY_ZONE": _buy_zone_label(p),
        "STOP_LOSS": _stop_label(p),
        "BINARY_EVENT": _binary_event_label(cats),
        "SPOT": p.spot,
        "PACKET_MODE": p.mode,
    }


def _count_words(text: str) -> int:
    return len(re.findall(r"\b[\w']+\b", text or ""))


def trading_note_structure_errors(text: str) -> list[str]:
    """Enforce 3 bullets + ~35–50 words for Layer-3 trading notes."""
    errs: list[str] = []
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    if len(lines) != 3:
        errs.append(f"need exactly 3 bullet lines, got {len(lines)}")
    for ln in lines:
        if not ln.lstrip().startswith(("•", "-", "*")):
            errs.append("each line must start with a bullet")
            break
    if lines:
        first = lines[0].lstrip("•-* ").strip()
        if not (first.startswith("🛑") or first.startswith("🚦") or first.startswith("🟢")):
            errs.append("first bullet must start with 🛑, 🚦, or 🟢")
    n = _count_words(text)
    if n < 30 or n > 55:
        # slightly soft band so deterministic notes aren't rejected for a few words
        errs.append(f"word count {n} outside 30–55")
    return errs


def render_plain_trading_notes(
    p: SignalPacket,
    c: ActionContract,
    cats: list["Catalyst"] | None = None,
) -> str:
    """Deterministic 10-second note: exactly 3 bullets, plain English, mode-aware."""
    payload = build_trading_note_payload(p, c, cats)
    emoji = payload["STATUS_EMOJI"]
    primary = payload["PRIMARY_ACTION"]
    mode = payload["MODE"]
    ticker = payload["TICKER"]
    zone = payload["BUY_ZONE"]
    stop = payload["STOP_LOSS"]
    cats_txt = payload["TOP_CATALYSTS"]
    cat1 = cats_txt[0] if cats_txt else "No fresh company catalyst"
    cat2 = cats_txt[1] if len(cats_txt) > 1 else None
    binary = payload["BINARY_EVENT"]
    starter = _starter_watch_zone(p)
    in_band = bool(p.entry_band and p.entry_band.contains(float(p.spot)))

    if primary == "AVOID":
        action = f"Avoid new buys in {ticker} — plan is broken until structure resets."
    elif primary == "CONFIRMED_BUY":
        action = f"Buy plan is clear for {ticker} — size only inside the listed zone."
    elif primary == "BUY_STARTER":
        action = f"Small starter only in {ticker} — do not treat this as a full buy."
    else:
        action = f"Wait on {ticker} — do not chase; buy only on a pullback into the zone."

    if binary != "NONE":
        driver = f"Near-term driver: {binary}."
        if cat2:
            driver = f"Near-term driver: {binary}; also watch {cat1.lower()}."
    elif cat2:
        driver = f"Main drivers: {cat1}; {cat2}."
    else:
        driver = f"Main driver: {cat1}."

    if mode == "DAY_TRADING":
        level = (
            f"Scalp only in {zone}; hard exit at {stop}."
            if zone != "n/a"
            else f"No clean scalp zone — stay flat; hard exit at {stop}."
        )
        line3 = f"• 🎯 SCALP LEVEL: {level}"
    elif mode == "LONG_TERM_INVESTOR":
        if starter:
            plan = f"Starter-size adds only in {zone}; walk away below {stop}."
        elif in_band:
            plan = f"Accumulate in {zone} for the long book; walk away below {stop}."
        else:
            plan = f"Add on a deeper dip into {zone}; walk away below {stop}."
        line3 = f"• 🎯 ACCUMULATION PLAN: {plan}"
    else:
        if in_band:
            band = f"Already in buy zone {zone}; keep a hard stop at {stop}."
        elif starter:
            band = f"Starter slice only in {zone}; hard stop at {stop}."
        else:
            band = f"Buy the pullback in {zone}; hard stop at {stop}."
        line3 = f"• 🎯 BUY ZONE & STOP: {band}"

    lines = [
        f"• {emoji} ACTION: {action}",
        f"• ⚠️ CATALYST & DRIVER: {driver}",
        line3,
    ]
    note = "\n".join(lines)
    if _count_words(note) > 55 and cat2:
        lines[1] = f"• ⚠️ CATALYST & DRIVER: Main driver: {cat1}."
        note = "\n".join(lines)
    return note


'''

NEW_SYSTEM = r'''SYSTEM_PROMPT = """You are a plain-English trading execution assistant for retail equity traders.
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
3. DYNAMIC STATUS EMOJI on the first bullet:
   - 🛑 if PRIMARY_ACTION is AVOID
   - 🚦 if PRIMARY_ACTION is WAIT_PULLBACK or BUY_STARTER
   - 🟢 if PRIMARY_ACTION is CONFIRMED_BUY
4. STRUCTURE: Output EXACTLY 3 bullet lines. No intro, no outro, no blank lines.
5. Every dollar figure and percentage MUST appear in EXECUTION_NOTE or PACKET. Never invent prices.
6. Never contradict PRIMARY_ACTION. Do not say BUY when action is AVOID or WAIT_PULLBACK.
7. Prefer TOP_CATALYSTS / BINARY_EVENT over technical jargon.

OUTPUT BY MODE (use EXECUTION_NOTE.MODE):

IF MODE == DAY_TRADING:
• [EMOJI] ACTION: [1 sentence intraday verdict]
• ⚠️ CATALYST & DRIVER: [1 sentence on today's flow / news / big-trader positioning]
• 🎯 SCALP LEVEL: [exact entry band + hard intraday stop]

IF MODE == SWING_TRADING:
• [EMOJI] ACTION: [1 sentence 1-2 week verdict]
• ⚠️ CATALYST & DRIVER: [earnings / macro / insider driver]
• 🎯 BUY ZONE & STOP: [pullback band + hard exit]

IF MODE == LONG_TERM_INVESTOR:
• [EMOJI] ACTION: [1 sentence long-term portfolio verdict]
• ⚠️ CATALYST & DRIVER: [valuation / rates / policy risk]
• 🎯 ACCUMULATION PLAN: [dip-buying zone for long-term adds]

Use STATUS_EMOJI from the payload when present. Output bullets only."""


'''

NEW_USER = r'''def build_user_prompt(p: SignalPacket, contract: ActionContract,
                      cats: list[Catalyst],
                      retail_scan: dict | None = None) -> str:
    """Structured execution payload first — keeps Layer-3 notes deterministic."""
    return json.dumps({
        "EXECUTION_NOTE": build_trading_note_payload(p, contract, cats),
        "PACKET": asdict(p),
        "ACTION_CONTRACT": {**asdict(contract), "action": contract.action.value},
        "RETAIL_SCAN": retail_scan or {},
        "CATALYSTS": [asdict(x) for x in cats],
    }, default=str)


'''


def replace_between(src: str, start: str, end: str, replacement: str) -> str:
    i = src.find(start)
    if i < 0:
        raise SystemExit(f"start not found: {start[:60]!r}")
    j = src.find(end, i)
    if j < 0:
        raise SystemExit(f"end not found after start: {end[:60]!r}")
    return src[:i] + replacement + src[j:]


# 1) Replace render_plain_trading_notes with helpers + new renderer
# Find start of render_plain_trading_notes and end at _is_news_catalyst
start = text.find("def render_plain_trading_notes(")
if start < 0:
    raise SystemExit("render_plain_trading_notes not found")
end = text.find("\ndef _is_news_catalyst(", start)
if end < 0:
    end = text.find("\ndef _is_news_catalyst(", start)
if end < 0:
    # alternate name
    for alt in ("\ndef _is_news_catalyst(", "\ndef _is_news_catalyst("):
        end = text.find(alt, start)
        if end >= 0:
            break
if end < 0:
    raise SystemExit("end marker for render_plain_trading_notes not found")

# Detect actual news helper name
news_helper = None
for name in ("_is_news_catalyst", "_is_news_catalyst", "_is_news_catalyst"):
    if f"def {name}(" in text[end:end + 80]:
        news_helper = name
        break
# peek
print("news helper peek:", repr(text[end:end + 40]))

text = text[:start] + HELPERS + text[end:]

# Fix helper dependency: HELPERS calls _is_news_catalyst — map to whatever exists
if "_is_news_catalyst" not in text and "def _is_news_catalyst(" in text:
    text = text.replace("_is_news_catalyst", "_is_news_catalyst")
if "def _is_news_catalyst(" in text and "_is_news_catalyst" in HELPERS:
    # keep as written; patch call if needed after detecting real name
    pass

# Detect real names for starter helper and news helper
import re as _re
m = _re.search(r"def (_is_news_\w+)\(", text)
news_fn = m.group(1) if m else "_is_news_catalyst"
m2 = _re.search(r"def (_starter_\w+)\(", text)
starter_fn = m2.group(1) if m2 else "_starter_watch_zone"
print("news_fn", news_fn, "starter_fn", starter_fn)
text = text.replace("_is_news_catalyst", news_fn)
# only replace our helper's call, not the def — already same if matched
text = text.replace("_starter_watch_zone", starter_fn)

# 2) Replace SYSTEM_PROMPT
sys_i = text.find("SYSTEM_PROMPT = \"\"\"")
if sys_i < 0:
    raise SystemExit("SYSTEM_PROMPT not found")
sys_j = text.find('"""', sys_i + 20)
sys_j = text.find('"""', sys_j + 3)  # closing
# include through trailing newlines before build_user_prompt
user_i = text.find("\ndef build_user_prompt(", sys_i)
if user_i < 0:
    raise SystemExit("build_user_prompt not found")
text = text[:sys_i] + NEW_SYSTEM + text[user_i + 1 :]

# 3) Replace build_user_prompt body
user_i = text.find("def build_user_prompt(")
user_end = text.find("\n\n# Matches", user_i)
if user_end < 0:
    user_end = text.find("\n\n# Matches", user_i)
if user_end < 0:
    user_end = text.find("\n_NUM_RE", user_i)
if user_end < 0:
    # find next def after build_user_prompt that isn't nested
    user_end = text.find("\ndef guard_numbers(", user_i)
if user_end < 0:
    raise SystemExit("could not find end of build_user_prompt")
print("user_end peek", repr(text[user_end:user_end+40]))
text = text[:user_i] + NEW_USER + text[user_end:].lstrip("\n")

# 4) NarrativeEngine: add structure validation + bump cache key
old_val = (
    "            bad_n = guard_numbers(text, p)\n"
    "            bad_w = layer3_banned_hits(text)\n"
    "            if not bad_n and not bad_w:\n"
)
new_val = (
    "            bad_n = guard_numbers(text, p)\n"
    "            bad_w = layer3_banned_hits(text)\n"
    "            bad_s = trading_note_structure_errors(text)\n"
    "            if not bad_n and not bad_w and not bad_s:\n"
)
# try alternate banned-hit name
if old_val not in text:
    for ban in ("layer3_banned_hits", "layer3_banned_hits", "layer3_banned_hits"):
        cand = old_val.replace("layer3_banned_hits", ban)
        if cand in text:
            old_val = cand
            new_val = new_val.replace("layer3_banned_hits", ban)
            break
if old_val not in text:
    # fuzzy find
    m = _re.search(
        r"bad_n = guard_numbers\(text, p\)\n\s+bad_w = (\w+)\(text\)\n\s+if not bad_n and not bad_w:\n",
        text,
    )
    if not m:
        raise SystemExit("validation block not found")
    ban = m.group(1)
    old_val = m.group(0)
    new_val = (
        f"bad_n = guard_numbers(text, p)\n"
        f"            bad_w = {ban}(text)\n"
        f"            bad_s = trading_note_structure_errors(text)\n"
        f"            if not bad_n and not bad_w and not bad_s:\n"
    )
text = text.replace(old_val, new_val, 1)

# rejection message append structure errors
old_rej = 'extra.append(f"forbidden jargon {bad_w} — rewrite in plain English")'
if old_rej in text:
    text = text.replace(
        old_rej,
        old_rej
        + '\n            if bad_s:\n'
        + '                extra.append(f"structure errors {bad_s} — exactly 3 bullets, 35-50 words, emoji on bullet 1")',
        1,
    )
else:
    # alternate wording
    m = _re.search(r'extra\.append\(f"forbidden[^\n]+"\)', text)
    if m:
        text = text.replace(
            m.group(0),
            m.group(0)
            + '\n            if bad_s:\n'
            + '                extra.append(f"structure errors {bad_s} — exactly 3 bullets, 35-50 words, emoji on bullet 1")',
            1,
        )

text = text.replace("narrative:v5:", "narrative:v6:", 1)
text = text.replace("v5 prioritizes", "v6 uses execution-note bullets;", 1)

PATH.write_text(text, encoding="utf-8")
print("patched", PATH)
print("has payload", "build_trading_note_payload" in text)
print("has SYSTEM day", "DAY_TRADING" in text)
print("has structure", "trading_note_structure_errors" in text)
print("cache v6", "narrative:v6:" in text)
