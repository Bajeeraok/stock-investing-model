"""
Phrase-level lexicons for commodity / precious-metal ETF news (GLD, SLV, USO, …).

Each entry: (phrase, base_score, weight_multiplier) with base_score +1 bullish / -1 bearish.
Matched case-insensitively as substrings against title + truncated body.
"""
from __future__ import annotations

# General commodity / broad-ETF terms
COMMODITY_ETF_LEXICON: list[tuple[str, int, float]] = [
    ("breakout",        +1, 1.2),
    ("momentum",        +1, 1.1),
    ("accumulation",    +1, 1.1),
    ("inflows",         +1, 1.2),
    ("etf inflow",      +1, 1.2),
    ("bullish",         +1, 1.2),
    ("upside",          +1, 1.1),
    ("support holds",   +1, 1.1),
    ("oversold",        +1, 1.1),
    ("breakdown",       -1, 1.2),
    ("outflows",        -1, 1.2),
    ("etf outflow",     -1, 1.2),
    ("bearish",         -1, 1.2),
    ("downside risk",   -1, 1.2),
    ("sell-off",        -1, 1.2),
    ("selloff",         -1, 1.2),
    ("support breaks",  -1, 1.2),
    ("resistance",      -1, 1.0),
]

GOLD_LEXICON: list[tuple[str, int, float]] = [
    ("safe haven",           +1, 1.4),
    ("inflation hedge",      +1, 1.4),
    ("flight to safety",     +1, 1.4),
    ("central bank buying",  +1, 1.4),
    ("rate cut",             +1, 1.3),
    ("fed pivot",            +1, 1.3),
    ("geopolitical risk",    +1, 1.3),
    ("geopolitical tension", +1, 1.3),
    ("stagflation",          +1, 1.3),
    ("gold rally",           +1, 1.3),
    ("dovish",               +1, 1.2),
    ("dollar weakness",      +1, 1.2),
    ("usd weakness",         +1, 1.2),
    ("weak dollar",          +1, 1.2),
    ("recession fear",       +1, 1.2),
    ("recession risk",       +1, 1.2),
    ("record high",          +1, 1.2),
    ("all-time high",        +1, 1.2),
    ("all time high",        +1, 1.2),
    ("demand surge",         +1, 1.2),
    ("spot rises",           +1, 1.1),
    ("gold gains",           +1, 1.1),
    ("gold advances",        +1, 1.1),
    ("uncertainty",          +1, 1.1),
    ("ceasefire",            +1, 1.1),
    ("war",                  +1, 1.2),
    ("conflict",             +1, 1.1),
    ("sanctions",            +1, 1.1),
    ("de-dollarization",     +1, 1.3),
    ("dedollarization",      +1, 1.3),
    ("spikes above",         +1, 1.2),
    ("spikes to",            +1, 1.2),
    ("edges higher",         +1, 1.1),
    ("trades higher",        +1, 1.1),
    ("moves higher",         +1, 1.1),
    ("month high",           +1, 1.2),
    ("year high",            +1, 1.2),
    ("demand soars",         +1, 1.2),
    ("demand rises",         +1, 1.1),
    ("investment demand",    +1, 1.1),
    ("consumption rises",    +1, 1.1),
    ("rate hike",            -1, 1.3),
    ("hawkish",              -1, 1.3),
    ("real rates up",        -1, 1.3),
    ("real yields rise",     -1, 1.3),
    ("dollar strength",      -1, 1.2),
    ("usd strength",         -1, 1.2),
    ("strong dollar",        -1, 1.2),
    ("risk-on",              -1, 1.2),
    ("risk on",              -1, 1.2),
    ("yields rise",          -1, 1.2),
    ("yields surge",         -1, 1.2),
    ("gold falls",           -1, 1.2),
    ("gold drops",           -1, 1.2),
    ("gold slides",          -1, 1.2),
    ("spot drops",           -1, 1.1),
    ("profit taking",        -1, 1.1),
    ("overbought",           -1, 1.1),
    ("taper",                -1, 1.2),
    ("quantitative tightening", -1, 1.2),
    ("qt",                   -1, 1.1),
]

SILVER_LEXICON: list[tuple[str, int, float]] = [
    ("solar demand",         +1, 1.4),
    ("solar panel",          +1, 1.3),
    ("supply deficit",       +1, 1.4),
    ("supply crunch",        +1, 1.4),
    ("green energy",         +1, 1.3),
    ("renewable energy",     +1, 1.3),
    ("ev demand",            +1, 1.2),
    ("electric vehicle",     +1, 1.2),
    ("industrial demand",    +1, 1.3),
    ("silver rally",         +1, 1.2),
    ("safe haven",           +1, 1.2),
    ("undervalued",          +1, 1.2),
    ("gold-silver ratio",    +1, 1.1),
    ("silver gains",         +1, 1.1),
    ("silver advances",      +1, 1.1),
    ("industrial slowdown",  -1, 1.3),
    ("manufacturing weak",   -1, 1.2),
    ("manufacturing pmi",    -1, 1.1),
    ("silver falls",         -1, 1.2),
    ("silver drops",         -1, 1.2),
    ("risk-off fades",       -1, 1.1),
    ("oversupply",           -1, 1.3),
]

GOLD_TICKERS = frozenset({"GLD", "IAU", "XAUUSD", "GOLD"})
SILVER_TICKERS = frozenset({"SLV", "XAGUSD", "PSLV", "SIVR"})

# ETFs / symbols that merge commodity word lexicon and/or phrase lexicon in news scoring
COMMODITY_LEXICON_TICKERS = frozenset({
    "GLD", "SLV", "IAU", "SGOL", "BAR", "OUNZ", "AAAU", "GLDM", "SIVR", "PSLV",
    "GDX", "GDXJ", "SIL", "RING", "USO", "UNG", "DBC", "COM", "BNO", "UGA",
}) | GOLD_TICKERS | SILVER_TICKERS

COMMODITY_PHRASE_SCORER_TICKERS = COMMODITY_LEXICON_TICKERS


def get_commodity_phrase_lexicon(sym: str) -> list[tuple[str, int, float]]:
    """Return merged phrase lexicon for a commodity / metals ticker."""
    t = sym.upper().replace(".", "-").split("-")[0].strip()
    if t in GOLD_TICKERS:
        return list(COMMODITY_ETF_LEXICON) + list(GOLD_LEXICON)
    if t in SILVER_TICKERS:
        return list(COMMODITY_ETF_LEXICON) + list(SILVER_LEXICON)
    return list(COMMODITY_ETF_LEXICON)
