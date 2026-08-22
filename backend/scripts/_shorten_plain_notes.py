# -*- coding: utf-8 -*-
from pathlib import Path

path = Path(__file__).resolve().parent.parent / "signals" / "narrative_waterfall.py"
text = path.read_text(encoding="utf-8")

start = text.find("def render_plain_trading_notes(")
end = text.find("\ndef _is_news_catalyst(", start)
if start < 0 or end < 0:
    raise SystemExit(f"markers missing start={start} end={end}")

new_fn = '''def render_plain_trading_notes(
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

    def _short(s: str, n: int = 70) -> str:
        s = (s or "").strip()
        return s if len(s) <= n else (s[: n - 1].rstrip() + "…")

    cat1 = _short(cats_txt[0] if cats_txt else "No fresh company catalyst")
    binary = payload["BINARY_EVENT"]
    starter = _starter_watch_zone(p)
    in_band = bool(p.entry_band and p.entry_band.contains(float(p.spot)))

    if primary == "AVOID":
        action = f"Avoid new buys in {ticker} — plan is broken for now."
    elif primary == "CONFIRMED_BUY":
        action = f"Buy plan is clear for {ticker} — size only in the zone."
    elif primary == "BUY_STARTER":
        action = f"Small starter only in {ticker} — not a full buy."
    else:
        action = f"Wait on {ticker} — do not chase; buy the pullback only."

    if binary != "NONE":
        driver = f"Near-term driver: {binary}."
    elif "no fresh company catalyst" in cat1.lower():
        driver = "No fresh company catalyst — this wait is about price and support."
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
            plan = f"Accumulate in {zone}; walk away below {stop}."
        else:
            plan = f"Add on a deeper dip into {zone}; walk away below {stop}."
        line3 = f"• 🎯 ACCUMULATION PLAN: {plan}"
    else:
        if in_band:
            band = f"Already in buy zone {zone}; hard stop at {stop}."
        elif starter:
            band = f"Starter slice only in {zone}; hard stop at {stop}."
        else:
            band = f"Buy the pullback in {zone}; hard stop at {stop}."
        line3 = f"• 🎯 BUY ZONE & STOP: {band}"

    return "\\n".join([
        f"• {emoji} ACTION: {action}",
        f"• ⚠️ CATALYST & DRIVER: {driver}",
        line3,
    ])


'''

# The above has escaped \\n in the source string which becomes \n in the file — we need real newline char
new_fn = new_fn.replace('return "\\n".join([', 'return "\\n".join([')
# Force correct: build with chr(10)
new_fn = new_fn.replace(
    'return "\\n".join([',
    'return chr(10).join([',
)

path.write_text(text[:start] + new_fn + text[end:], encoding="utf-8")
print("rewrote render_plain_trading_notes")
