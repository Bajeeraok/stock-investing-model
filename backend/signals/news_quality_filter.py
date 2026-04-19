"""
Domain + headline quality for news before keyword lexicon scoring.

Tiered domain weights and headline-pattern multipliers; combined weight
is used to downweight or exclude articles in aggregate_keyword_sentiment.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

# ── Domain quality tiers (see module docstring in original design) ───────────

DOMAIN_WEIGHTS: dict[str, float] = {

    # Tier A — primary / wire
    "reuters.com":              1.0,
    "bloomberg.com":            1.0,
    "wsj.com":                  1.0,
    "ft.com":                   1.0,
    "apnews.com":               1.0,
    "sec.gov":                  1.0,
    "federalreserve.gov":       1.0,
    "bls.gov":                  1.0,
    "cnbc.com":                 0.9,
    "marketwatch.com":          0.9,
    "barrons.com":              0.9,
    "economist.com":            0.9,

    # Tier B
    "finance.yahoo.com":        0.8,
    "investing.com":            0.75,
    "financialtimes.com":       0.9,
    "morningstar.com":          0.8,
    "zacks.com":                  0.75,
    "benzinga.com":             0.7,
    "thestreet.com":            0.65,
    "fool.com":                 0.4,
    "motleyfool.com":           0.4,

    # Tier C
    "seekingalpha.com":         0.5,
    "stockanalysis.com":        0.65,
    "gurufocus.com":            0.6,
    "macrotrends.net":          0.6,
    "tradingeconomics.com":     0.65,
    "businessinsider.com":      0.6,
    "forbes.com":               0.6,
    "fortune.com":              0.65,

    # Tier D
    "247wallst.com":            0.2,
    "24/7wallst.com":           0.2,
    "schaeffersresearch.com":   0.3,
    "investorplace.com":        0.3,
    "kiplinger.com":            0.35,
    "smarteranalyst.com":       0.2,
    "direxion.com":             0.3,
    "etftrends.com":            0.5,

    # Blocked
    "prnewswire.com":           0.0,
    "businesswire.com":         0.0,
    "globenewswire.com":        0.0,
    "accesswire.com":           0.0,
    "newswire.com":             0.0,
    "sec.report":               0.0,
    "form4transactions.com":    0.0,
    "insidearbitrage.com":      0.15,
    "simplywall.st":            0.3,
}

DEFAULT_DOMAIN_WEIGHT = 0.6

# (pattern, multiplier, reason)
HEADLINE_PATTERN_FILTERS: list[tuple[str, float, str]] = [

    (r"shares (sold|purchased|acquired|disposed) by",       0.0,  "institutional filing"),
    (r"(reduces|increased|trimmed|raised) (stake|position|holdings)", 0.05, "position change filing"),
    (r"\$[\d,.]+ million (stock |share )?holdings? in",     0.0,  "13F filing disclosure"),
    (r"(13[fg]|form 4|sc 13[dg])",                          0.0,  "SEC filing"),
    (r"(bought|sold) \$[\d,.]+ (million|billion|worth)",    0.05, "position size disclosure"),

    (r"^(is |are |should |can |will |does |why |how |what |when )", 0.4,  "question-lead SEO"),
    (r"\b(top \d+|best \d+|\d+ (stock|reason|way)s? to)\b", 0.3,  "listicle"),
    (r"\b(buy or sell|buy, sell|hold or sell)\b",           0.35, "buy/sell framing SEO"),
    (r"only one deserves",                                   0.1,  "clickbait comparison"),
    (r"(apple|amazon|microsoft|meta|nvidia|tesla) vs (alphabet|google|googl)", 0.3, "comparison clickbait"),
    (r"got \$[\d,]+\?",                                      0.1,  "investment-amount SEO"),
    (r"here'?s? (why|what|how)",                            0.35, "SEO explainer"),
    (r"everything you need to know",                         0.2,  "SEO explainer"),
    (r"what (makes|is) .{3,30} (a )?(buy|sell|hold|stock)", 0.3,  "evergreen SEO"),

    (r"(spy|qqq|aapl|msft|nvda|googl|meta|tsla).{0,10}(spy|qqq|aapl|msft|nvda|googl|meta|tsla).{0,10}(spy|qqq|aapl|msft|nvda|googl|meta|tsla)",
                                                             0.25, "multi-ticker roundup"),
    (r"trade strategy for .{5,50}and",                      0.25, "multi-ticker strategy"),
    (r"stocks? to (watch|buy|avoid) (this week|today|now|in \d{4})",
                                                             0.3,  "market roundup"),
    (r"charts? to watch",                                     0.22, "chart roundup / multi-asset"),
    (r"\b(solid|top|best) .{0,40}\b(stocks?|picks?)\b.{0,30}\b(as|to)\b",
                                                             0.22, "multi-ticker listicle"),
    (r"\bstocks? to (grab|snag|own)\b",                       0.24, "listicle CTA"),
    (r"\b(takeover|merger) talk\b|\bstirs.{0,30}(buzz|speculation)", 0.25, "rumor / takeover chatter"),
    (r"\b(hinges on|volatility).{0,50}(iran|china|tariff|geopolitical|middle east)\b|"
     r"\b(geopolitical|iran).{0,40}(volatility|hinges|risk)\b",
                                                             0.22, "geopolitical macro headline"),
    (r"\b(saas|semiconductor|tech).{0,20}(recovery|strength).{0,40}(hinges|depends)\b",
                                                             0.25, "thematic macro roundup"),

    (r"wall street analyst(s)? (see|target|expect|consensus|look)", 0.4, "analyst consensus summary"),
    (r"price target (raised|lowered|cut|increased) to",     0.7,  "analyst PT change — keep but downweight"),
    (r"(initiated|reiterated|upgraded|downgraded).{0,20}(buy|sell|hold|neutral|overweight|underweight)",
                                                             0.8,  "analyst rating — meaningful"),

    (r"(earnings|revenue|profit).{0,20}(beat|miss|surpass|exceed|disappoint)",
                                                             1.12, "earnings result — high signal"),
    (r"(guidance|outlook).{0,20}(raised|lowered|cut|above|below|reaffirm)",
                                                             1.12, "guidance change — high signal"),
    (r"(antitrust|regulation|lawsuit|doj|ftc|eu).{0,30}(alphabet|google|googl)",
                                                             1.2,  "regulatory — high signal"),
    (r"(layoff|restructur|reorg|job cut)",                   1.1,  "restructuring — moderate signal"),
    (r"(acquisition|merger|acquires|buys|deal worth)",       1.2,  "M&A — high signal"),
    (r"(share buyback|repurchase program|dividend)",         1.1,  "capital return — moderate signal"),
]


def get_domain_weight(url_or_source: str | None) -> float:
    if not url_or_source:
        return DEFAULT_DOMAIN_WEIGHT

    raw = url_or_source.lower().strip()
    try:
        parsed = urlparse(raw if raw.startswith("http") else f"https://{raw}")
        domain = parsed.netloc or parsed.path.split("/")[0]
        domain = re.sub(r"^www\.", "", domain)
    except Exception:
        domain = raw

    if domain in DOMAIN_WEIGHTS:
        return DOMAIN_WEIGHTS[domain]

    for known, weight in DOMAIN_WEIGHTS.items():
        if domain.endswith(known) or known.endswith(domain):
            return weight

    return DEFAULT_DOMAIN_WEIGHT


def get_headline_pattern_weight(title: str) -> tuple[float, str]:
    if not title:
        return 1.0, ""

    title_lower = title.lower()
    best_multiplier = 1.0
    best_reason = ""

    for pattern, multiplier, reason in HEADLINE_PATTERN_FILTERS:
        if re.search(pattern, title_lower):
            if multiplier < 1.0 and multiplier < best_multiplier:
                best_multiplier = multiplier
                best_reason = reason
            elif multiplier > 1.0 and best_multiplier >= 1.0:
                best_multiplier = multiplier
                best_reason = reason

    return best_multiplier, best_reason


def compute_quality_weight(
    title: str,
    url_or_source: str | None = None,
) -> tuple[float, str]:
    domain_w = get_domain_weight(url_or_source)
    pattern_w, reason = get_headline_pattern_weight(title)

    # Cap positive pattern boosts so SEO domains cannot inherit “earnings beat” multipliers at full strength.
    if pattern_w > 1.0:
        max_boost = 1.0 + 0.15 * domain_w
        pattern_w = min(pattern_w, max_boost)

    combined = round(min(1.0, domain_w * pattern_w), 4)

    label_parts = []
    if domain_w < DEFAULT_DOMAIN_WEIGHT:
        label_parts.append(f"domain={domain_w:.1f}")
    if reason:
        label_parts.append(reason)

    reason_str = "; ".join(label_parts) if label_parts else "ok"
    return combined, reason_str


def filter_headlines(
    headlines: list[dict],
    min_quality: float = 0.20,
) -> list[dict]:
    result = []
    for h in headlines:
        title = h.get("title") or ""
        url = (
            h.get("url")
            or h.get("site")
            or h.get("source")
            or h.get("publisher")
            or ""
        )
        qw, reason = compute_quality_weight(title, url)

        enriched = {**h, "quality_weight": qw, "quality_reason": reason}

        if qw >= min_quality:
            result.append(enriched)

    return result
