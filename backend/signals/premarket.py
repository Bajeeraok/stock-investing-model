"""
Pre-market snapshot: ES/NQ futures and basket (mega-cap tech vs value/cyclicals) vs prior close.
Labels rotation risk when futures soft and tech red, value flat/green.
"""
from __future__ import annotations

try:
    import yfinance as yf
except ImportError:
    yf = None

# Futures symbols (Yahoo)
ES_SYMBOL = "ES=F"
NQ_SYMBOL = "NQ=F"

# Mega-cap tech and value/cyclical ETFs for pre-market move
PREMARKET_TECH = ["AAPL", "MSFT", "META", "NVDA", "GOOGL", "GOOG", "NFLX", "TSLA"]
PREMARKET_VALUE = ["XLF", "XLE", "XLI"]


def _fetch_prior_close_and_last(symbol: str) -> tuple[float | None, float | None]:
    """Returns (prior_close, last_price). Uses 5d to get prior close and latest."""
    if not yf:
        return None, None
    try:
        data = yf.download(symbol, period="5d", progress=False, threads=False, auto_adjust=True)
        if data is None or data.empty or len(data) < 2:
            return None, None
        close_col = data.get("Close")
        if close_col is None and hasattr(data, "columns"):
            for c in ("Adj Close", "Close"):
                if c in data.columns:
                    close_col = data[c]
                    break
        if close_col is None:
            close_col = data.iloc[:, 0]
        prior = float(close_col.iloc[-2])
        last = float(close_col.iloc[-1])
        return prior, last
    except Exception:
        return None, None


def _pct_change(prior: float | None, last: float | None) -> float | None:
    if prior is None or last is None or prior <= 0:
        return None
    return round(100 * (last - prior) / prior, 2)


def run_premarket_snapshot() -> dict:
    """
    Fetch ES, NQ and basket vs prior close.
    Returns:
      es_pct, nq_pct: futures % vs prior
      tech_avg_pct, value_avg_pct: average % for baskets
      rotation_risk_premarket: Low | Medium | High
      message: one-line banner text
    """
    out = {
        "es_pct": None,
        "nq_pct": None,
        "tech_avg_pct": None,
        "value_avg_pct": None,
        "rotation_risk_premarket": "Low",
        "message": None,
        "tech_movers": [],
        "value_movers": [],
    }

    if not yf:
        return out

    es_prior, es_last = _fetch_prior_close_and_last(ES_SYMBOL)
    nq_prior, nq_last = _fetch_prior_close_and_last(NQ_SYMBOL)
    out["es_pct"] = _pct_change(es_prior, es_last)
    out["nq_pct"] = _pct_change(nq_prior, nq_last)

    tech_pcts = []
    for t in PREMARKET_TECH:
        prior, last = _fetch_prior_close_and_last(t)
        pct = _pct_change(prior, last)
        if pct is not None:
            tech_pcts.append(pct)
            out["tech_movers"].append({"ticker": t, "pct": pct})
    value_pcts = []
    for t in PREMARKET_VALUE:
        prior, last = _fetch_prior_close_and_last(t)
        pct = _pct_change(prior, last)
        if pct is not None:
            value_pcts.append(pct)
            out["value_movers"].append({"ticker": t, "pct": pct})

    if tech_pcts:
        out["tech_avg_pct"] = round(sum(tech_pcts) / len(tech_pcts), 2)
    if value_pcts:
        out["value_avg_pct"] = round(sum(value_pcts) / len(value_pcts), 2)

    # Rotation risk: NQ meaningfully weaker than ES, tech red, value flat/green
    nq_pct = out["nq_pct"]
    es_pct = out["es_pct"]
    tech_avg = out["tech_avg_pct"]
    value_avg = out["value_avg_pct"]

    if nq_pct is not None and es_pct is not None:
        nq_under_es = nq_pct < es_pct - 0.3  # NQ at least 0.3% weaker than ES
    else:
        nq_under_es = False

    tech_red = tech_avg is not None and tech_avg < -0.2
    value_flat_or_green = value_avg is None or value_avg >= -0.1

    if nq_under_es and tech_red and value_flat_or_green:
        out["rotation_risk_premarket"] = "High"
        out["message"] = "Pre-market: Futures soft, mega-cap tech underperforming vs value/cyclicals → rotation risk HIGH; tighten tech buy zones, favor holds/trims."
    elif (tech_red and value_flat_or_green) or nq_under_es:
        out["rotation_risk_premarket"] = "Medium"
        out["message"] = "Pre-market: Tech weak vs value/cyclicals or NQ underperforming ES → rotation risk elevated."
    else:
        out["message"] = "Pre-market: No strong rotation signal."

    return out
