"""Backend fixes: stop below entry, news competitive threats, base-case floor, zone-state notes."""
from pathlib import Path
import re

ROOT = Path(r"C:\Users\hegunda\stock-investing-model")

# ── 1) narrative_packet_mapper: clamp stop below entry floor ─────────────────
mapper = ROOT / "backend/signals/narrative_packet_mapper.py"
mt = mapper.read_text(encoding="utf-8")

helper = '''
def _stop_below_entry_floor(
    stop_loss: float | None,
    entry_band: Band | None,
    spot: float,
) -> float | None:
    """Hard rule: tactical stop must sit below the add-zone floor.

    Stops that land inside the entry band make R:R look absurd (tiny risk leg)
    and can stop out while the trader is still building into the zone.
    """
    if stop_loss is None:
        return None
    stop = float(stop_loss)
    if entry_band is None:
        return stop
    floor = float(entry_band.lo)
    if stop < floor - 1e-9:
        return stop
    # Park stop just under the floor; keep at least ~1.5% of spot of buffer when possible.
    buf = max(spot * 0.015, floor * 0.008, 0.05) if spot > 0 else max(floor * 0.008, 0.05)
    return round(floor - buf, 2)

'''

if "_stop_below_entry_floor" not in mt:
    # insert before _owner_entry_band or after _usable_live_floor
    anchor = "def _owner_entry_band("
    if anchor not in mt:
        anchor = "def _invalidation("
    mt = mt.replace(anchor, helper + anchor, 1)

old_block = """    stop_loss = horizon.get("stop_loss")
    inv = _invalidation(horizon, mode, stop_loss, spot)
    rr = None
    if horizon.get("risk_reward") is not None:
        rr = float(horizon["risk_reward"])
    if stop_loss is not None and horizon.get("target") is not None and spot > float(stop_loss):
        tgt = float(horizon["target"])
        if tgt > spot:
            computed_rr = (tgt - spot) / (spot - float(stop_loss))
            rr = round(computed_rr, 2)
"""

new_block = """    stop_loss = horizon.get("stop_loss")
    if stop_loss is not None:
        stop_loss = _stop_below_entry_floor(float(stop_loss), entry_band, spot)
    inv = _invalidation(horizon, mode, stop_loss, spot)
    rr = None
    if horizon.get("risk_reward") is not None:
        rr = float(horizon["risk_reward"])
    if stop_loss is not None and horizon.get("target") is not None and spot > float(stop_loss):
        tgt = float(horizon["target"])
        if tgt > spot:
            computed_rr = (tgt - spot) / (spot - float(stop_loss))
            rr = round(computed_rr, 2)
"""

if old_block in mt:
    mt = mt.replace(old_block, new_block)
    print("mapper stop clamp OK")
else:
    print("WARN mapper stop block not exact — check manually")

mapper.write_text(mt, encoding="utf-8")

# Also tighten validate(): stop >= entry_lo always errors (even when waiting)
nw = ROOT / "backend/signals/narrative_waterfall.py"
nt = nw.read_text(encoding="utf-8")
old_v = """        if (
            self.stop
            and self.entry_band
            and self.stop >= self.entry_band.lo
            and not waiting
        ):
            errs.append("stop >= entry band low")
"""
new_v = """        # Always keep stop under the add-zone floor (waiting-above plans included).
        if self.stop and self.entry_band and self.stop >= self.entry_band.lo:
            errs.append("stop >= entry band low")
"""
if old_v in nt:
    nt = nt.replace(old_v, new_v)
    print("validate stop rule tightened")
elif "stop >= entry band low" in nt:
    print("validate already different; leaving")
else:
    print("WARN validate stop rule missing")

# ── 2) Zone-state in plain notes + retail scan + LLM prompt ─────────────────
# Fix render_plain_trading_notes "A dip into" when already inside
old_notes = """    starter = _starter_watch_zone(p)
    if p.entry_band:
        cool = ""
        if p.rsi is not None and float(p.rsi) >= 50:
            cool = " after the move cools off"
        if starter:
            bits.append(
                f"A dip into {p.entry_band.fmt()}{cool} is a small first slice at most — "
                "not a full buy."
            )
            if p.full_size_price:
                bits.append(
                    f"A full-size buy still needs a cheaper price, around ${p.full_size_price:,.2f}."
                )
        else:
            bits.append(f"The planned buy area is {p.entry_band.fmt()}{cool}.")
"""

new_notes = """    starter = _starter_watch_zone(p)
    if p.entry_band:
        cool = ""
        if p.rsi is not None and float(p.rsi) >= 50:
            cool = " after the move cools off"
        in_band = bool(p.entry_band.contains(p.spot)) if hasattr(p.entry_band, "contains") else (
            p.entry_band.lo - 1e-6 <= float(p.spot) <= p.entry_band.hi + 1e-6
        )
        above = float(p.spot) > p.entry_band.hi + 1e-6
        if in_band:
            bits.append(
                f"Price is already INSIDE the buy zone {p.entry_band.fmt()}"
                f"{' — starter only, not full size' if starter else ''}."
            )
            if starter and p.full_size_price:
                bits.append(
                    f"A full-size buy still needs a cheaper price, around ${p.full_size_price:,.2f}."
                )
        elif above:
            if starter:
                bits.append(
                    f"Wait for a pullback into {p.entry_band.fmt()}{cool} — small first slice at most, "
                    "not a full buy."
                )
                if p.full_size_price:
                    bits.append(
                        f"A full-size buy still needs a cheaper price, around ${p.full_size_price:,.2f}."
                    )
            else:
                bits.append(
                    f"Wait for a pullback into {p.entry_band.fmt()}{cool} before adding."
                )
        else:
            bits.append(f"The planned buy area is {p.entry_band.fmt()}{cool}.")
"""

if old_notes in nt:
    nt = nt.replace(old_notes, new_notes)
    print("plain notes zone-state OK")
else:
    print("WARN plain notes block not found")

# Retail scan: add zone state line
old_scan = """    if p.entry_band:
        buy = f"✅ Buy zone: {p.entry_band.fmt()}{rsi_clause}"
        if starter:
            buy += " — starter only, not full size"
        lines.append(buy)
        lines.append(f"❌ Never chase above ${p.entry_band.hi:,.2f}")
"""
new_scan = """    if p.entry_band:
        in_band = p.entry_band.lo - 1e-6 <= float(p.spot) <= p.entry_band.hi + 1e-6
        if in_band:
            zone = f"📍 Zone: ${p.spot:,.2f} is INSIDE buy zone {p.entry_band.fmt()}"
        elif float(p.spot) > p.entry_band.hi:
            zone = f"📍 Zone: ${p.spot:,.2f} is ABOVE buy zone {p.entry_band.fmt()} — wait for pullback"
        else:
            zone = f"📍 Zone: ${p.spot:,.2f} is BELOW buy zone {p.entry_band.fmt()}"
        if starter:
            zone += " (starter only)"
        lines.append(zone)
        buy = f"✅ Buy zone: {p.entry_band.fmt()}{rsi_clause}"
        if starter:
            buy += " — starter only, not full size"
        lines.append(buy)
        lines.append(f"❌ Never chase above ${p.entry_band.hi:,.2f}")
"""
if old_scan in nt:
    nt = nt.replace(old_scan, new_scan)
    # allow 5 lines now that we added zone
    nt = nt.replace("    lines = lines[:4]", "    lines = lines[:5]", 1)
    print("retail scan zone line OK")
else:
    print("WARN retail scan block not found")

# LLM hard rule for zone state
if "price_in_buy_zone" not in nt:
    nt = nt.replace(
        '10. If CATALYSTS has no News:/Known event: items, you MUST say there is no fresh company catalyst in the packet (earnings, deal, guidance) — then stick to timing/price conditions. Never invent institutions buying, bull conditions, or a headline.\n'
        '11. Tone: calm, specific, no hype."""',
        '10. If CATALYSTS has no News:/Known event: items, you MUST say there is no fresh company catalyst in the packet (earnings, deal, guidance) — then stick to timing/price conditions. Never invent institutions buying, bull conditions, or a headline.\n'
        '11. Tone: calm, specific, no hype.\n'
        '12. ZONE STATE (hard fact): If RETAIL_SCAN / PACKET says price is INSIDE the buy zone, you MUST NOT say \"wait for a pullback into\" that same zone. Say price is already in the band and name the real blocker (gates / weather / confidence).\n'
        '13. Catalyst line: only mention calendar/news catalysts listed in CATALYSTS. Frame them relative to the verdict (never call competitive-threat headlines \"bullish\" on your own)."""',
    )
    print("LLM zone/catalyst rules added")

nw.write_text(nt, encoding="utf-8")

# ── 3) News: competitive-threat phrases; remove bare "deal" as bullish ───────
news = ROOT / "backend/signals/news_keyword_sentiment.py"
if not news.exists():
    news = ROOT / "backend/signals/news_keyword_sentiment.py"
ntxt = news.read_text(encoding="utf-8")
# Remove bare deal/deals from bullish set if present
ntxt2 = ntxt.replace('"deal", "deals", ', "")
ntxt2 = ntxt2.replace('"partnership",\n    "partnerships", ', '"partnership",\n    "partnerships", ')
# Add competitive threat phrases
marker = "_BEARISH_PHRASES = ("
extra = '''_BEARISH_PHRASES = (
    "competitive threat",
    "competitor win",
    "loses share",
    "losing share",
    "share loss",
    "takes share",
    "taking share",
    "market share loss",
    "custom silicon",
    "in-house chip",
    "in-house asic",
    "google tpu",
    "rival chip",
    "customer designs own",
'''
if "google tpu" not in ntxt2 and marker in ntxt2:
    ntxt2 = ntxt2.replace(marker, extra, 1)
    print("news competitive phrases OK")
news.write_text(ntxt2, encoding="utf-8")

# Strengthen reconcile: stormy/DOWN tape + bullish chip without unlocks -> Mixed
rec = ROOT / "backend/signals/news_sentiment_reconcile.py"
if not rec.exists():
    rec = ROOT / "backend/signals/news_sentiment_reconcile.py"
rt = rec.read_text(encoding="utf-8")
if "competitive" not in rt:
    # extend bear title regex
    rt = rt.replace(
        r'"crash|layoff)\b",',
        r'"crash|layoff|competitor|competitive|tpu|asic|share\\s+loss|losing\\s+share)\b",',
    )
    rec.write_text(rt, encoding="utf-8")
    print("reconcile bear titles extended")

# ── 4) Base-case probability floor ───────────────────────────────────────────
sc = ROOT / "backend/signals/scenario_regime_aware.py"
st = sc.read_text(encoding="utf-8")
old_else = """        else:
            # Neutral scenarios (base_case) — small adjustment toward bear in bear regime
            adj_prob = s.base_probability * (1.0 + (factor - 1.0) * 0.3)
"""
new_else = """        else:
            # Neutral scenarios (base_case) — small adjustment toward bear in bear regime.
            # Floor at 10% of original mass so UI never shows \"Base Case · 0% prob\".
            adj_prob = s.base_probability * (1.0 + (factor - 1.0) * 0.3)
            adj_prob = max(adj_prob, max(0.08, 0.35 * float(s.base_probability or 0.0)))
"""
if old_else in st:
    st = st.replace(old_else, new_else)
    sc.write_text(st, encoding="utf-8")
    print("base-case floor OK")
else:
    print("WARN scenario else-block not found")

print("backend fixes done")
