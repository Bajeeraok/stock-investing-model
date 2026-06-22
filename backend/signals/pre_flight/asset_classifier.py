"""
Thrive Alpha — Asset Classifier
Pre-flight routing layer that runs BEFORE main signal fusion.
Determines asset type, adjusts layer weights, and generates pre-flight flags.
"""

from typing import Dict, Optional
from .constants import AssetType, FlagType, WEIGHT_PROFILES
from .models import AssetMeta, ClassificationResult, PreFlightFlag
from .asset_registry_cache import get_inferred_meta, save_inferred_meta
from .asset_registry_infer import infer_asset_meta_from_ticker


# ─────────────────────────────────────────────
# ASSET REGISTRY
# ─────────────────────────────────────────────

ASSET_REGISTRY: Dict[str, AssetMeta] = {
    # ── US Equities ──────────────────────────
    "GOOGL": AssetMeta(ticker="GOOGL", name="Alphabet Inc.", asset_type=AssetType.EQUITY_US,
                       sector="Technology", beta=1.1),
    "NVDA":  AssetMeta(ticker="NVDA", name="NVIDIA Corp", asset_type=AssetType.EQUITY_US,
                       sector="Technology", beta=1.8),
    "SMCI":  AssetMeta(ticker="SMCI", name="Super Micro Computer", asset_type=AssetType.EQUITY_US,
                       sector="Technology", beta=2.5,
                       sentiment_amplified=True),
    "AVGO":  AssetMeta(ticker="AVGO", name="Broadcom Inc", asset_type=AssetType.EQUITY_US,
                       sector="Technology", beta=1.2),
    "AAPL":  AssetMeta(ticker="AAPL", name="Apple Inc.", asset_type=AssetType.EQUITY_US,
                       sector="Technology", beta=1.2),
    "MSFT":  AssetMeta(ticker="MSFT", name="Microsoft Corp", asset_type=AssetType.EQUITY_US,
                       sector="Technology", beta=0.9),
    "AMZN":  AssetMeta(ticker="AMZN", name="Amazon.com Inc", asset_type=AssetType.EQUITY_US,
                       sector="Consumer Discretionary", beta=1.3),
    "META":  AssetMeta(ticker="META", name="Meta Platforms", asset_type=AssetType.EQUITY_US,
                       sector="Technology", beta=1.3),
    "BRK-B": AssetMeta(ticker="BRK-B", name="Berkshire Hathaway B", asset_type=AssetType.EQUITY_US,
                       sector="Financials", beta=0.9,
                       insider_data_reliable=False,
                       insider_note="Berkshire rarely trades own stock — insider signal structurally weak"),
    "XOM":   AssetMeta(ticker="XOM", name="ExxonMobil Corp", asset_type=AssetType.EQUITY_US,
                       sector="Energy", beta=1.1,
                       macro_sensitive=True, macro_driver="Oil prices (WTI/Brent)"),
    "JPM":   AssetMeta(ticker="JPM", name="JPMorgan Chase", asset_type=AssetType.EQUITY_US,
                       sector="Financials", beta=1.1,
                       macro_sensitive=True, macro_driver="Interest rates, credit spreads"),

    # ── Speculative / High Beta ──────────────
    "TSLA":  AssetMeta(ticker="TSLA", name="Tesla Inc", asset_type=AssetType.EQUITY_SPECULATIVE,
                       sector="Consumer Cyclical", beta=2.3,
                       sentiment_amplified=True),
    "PLTR":  AssetMeta(ticker="PLTR", name="Palantir Technologies", asset_type=AssetType.EQUITY_SPECULATIVE,
                       sector="Technology", beta=2.1,
                       sentiment_amplified=True),
    "MSTR":  AssetMeta(ticker="MSTR", name="MicroStrategy Inc", asset_type=AssetType.EQUITY_SPECULATIVE,
                       sector="Technology", beta=3.2,
                       sentiment_amplified=True,
                       macro_sensitive=True, macro_driver="Bitcoin price"),
    "COIN":  AssetMeta(ticker="COIN", name="Coinbase Global", asset_type=AssetType.EQUITY_SPECULATIVE,
                       sector="Financials", beta=2.8,
                       sentiment_amplified=True),

    # ── Defensive ────────────────────────────
    "KO":    AssetMeta(ticker="KO", name="Coca-Cola Co", asset_type=AssetType.EQUITY_DEFENSIVE,
                       sector="Consumer Staples", beta=0.6),
    "JNJ":   AssetMeta(ticker="JNJ", name="Johnson & Johnson", asset_type=AssetType.EQUITY_DEFENSIVE,
                       sector="Healthcare", beta=0.5),
    "PG":    AssetMeta(ticker="PG", name="Procter & Gamble", asset_type=AssetType.EQUITY_DEFENSIVE,
                       sector="Consumer Staples", beta=0.5),
    "VZ":    AssetMeta(ticker="VZ", name="Verizon Communications", asset_type=AssetType.EQUITY_DEFENSIVE,
                       sector="Telecom", beta=0.4),

    # ── ADRs / Foreign ───────────────────────
    "BABA":  AssetMeta(ticker="BABA", name="Alibaba Group", asset_type=AssetType.EQUITY_ADR,
                       sector="Consumer Cyclical", country="China",
                       insider_data_reliable=False,
                       insider_note="Chinese ADR — SEC insider disclosure limited",
                       geopolitical_risk=True),
    "BIDU":  AssetMeta(ticker="BIDU", name="Baidu Inc", asset_type=AssetType.EQUITY_ADR,
                       sector="Technology", country="China",
                       insider_data_reliable=False,
                       insider_note="Chinese ADR — SEC insider disclosure limited",
                       geopolitical_risk=True),
    "TSM":   AssetMeta(ticker="TSM", name="Taiwan Semiconductor", asset_type=AssetType.EQUITY_ADR,
                       sector="Technology", country="Taiwan",
                       insider_data_reliable=False,
                       insider_note="Taiwanese ADR — insider disclosure limited",
                       geopolitical_risk=True,
                       macro_sensitive=True, macro_driver="US-China relations, semiconductor cycle"),
    "NVO":   AssetMeta(ticker="NVO", name="Novo Nordisk", asset_type=AssetType.EQUITY_ADR,
                       sector="Healthcare", country="Denmark",
                       insider_data_reliable=False,
                       insider_note="Danish ADR — insider disclosure limited"),
    "ASML":  AssetMeta(ticker="ASML", name="ASML Holding NV", asset_type=AssetType.EQUITY_ADR,
                       sector="Technology", country="Netherlands",
                       insider_data_reliable=False,
                       insider_note="Dutch ADR — insider disclosure limited",
                       macro_sensitive=True, macro_driver="Semiconductor export restrictions"),

    # ── ETFs — Equity ─────────────────────────
    "OIH":   AssetMeta(ticker="OIH", name="VanEck Oil Services ETF", asset_type=AssetType.ETF_EQUITY,
                       sector="Oil Services ETF",
                       insider_data_reliable=False,
                       fundamentals_applicable=False,
                       insider_note="ETF — no insider activity applicable",
                       fundamentals_note="ETF — use NAV / sector view, not EPS/PE",
                       macro_sensitive=True, macro_driver="Oil prices (WTI), energy sector sentiment"),
    "IWM":   AssetMeta(ticker="IWM", name="iShares Russell 2000 ETF", asset_type=AssetType.ETF_EQUITY,
                       sector="Small Cap ETF",
                       insider_data_reliable=False,
                       fundamentals_applicable=False,
                       insider_note="ETF — no insider applicable",
                       fundamentals_note="ETF — index product, no single-stock EPS/PE"),
    "ARKK":  AssetMeta(ticker="ARKK", name="ARK Innovation ETF", asset_type=AssetType.ETF_EQUITY,
                       sector="Innovation ETF",
                       insider_data_reliable=False,
                       fundamentals_applicable=False,
                       insider_note="ETF — no insider activity applicable",
                       fundamentals_note="ETF — use NAV analysis, not EPS/PE"),
    "QQQ":   AssetMeta(ticker="QQQ", name="Invesco QQQ Trust", asset_type=AssetType.ETF_EQUITY,
                       sector="Tech ETF",
                       insider_data_reliable=False, fundamentals_applicable=False,
                       insider_note="ETF — no insider applicable",
                       fundamentals_note="ETF — index product, no EPS/PE"),
    "SPY":   AssetMeta(ticker="SPY", name="SPDR S&P 500 ETF", asset_type=AssetType.ETF_EQUITY,
                       sector="Broad Market ETF",
                       insider_data_reliable=False, fundamentals_applicable=False,
                       insider_note="ETF — no insider applicable",
                       fundamentals_note="ETF — index product"),

    # ── ETFs — Commodity ─────────────────────
    "GLD":   AssetMeta(ticker="GLD", name="SPDR Gold Shares", asset_type=AssetType.ETF_COMMODITY,
                       sector="Gold ETF",
                       insider_data_reliable=False, fundamentals_applicable=False,
                       insider_note="Commodity ETF — no insider applicable",
                       fundamentals_note="Commodity — no EPS/PE. Use macro layer.",
                       macro_sensitive=True, macro_driver="USD strength, real yields, inflation"),
    "SLV":   AssetMeta(ticker="SLV", name="iShares Silver Trust", asset_type=AssetType.ETF_COMMODITY,
                       sector="Silver ETF",
                       insider_data_reliable=False, fundamentals_applicable=False,
                       insider_note="Commodity ETF — no insider applicable",
                       fundamentals_note="Commodity — no EPS/PE",
                       macro_sensitive=True, macro_driver="USD, industrial demand, inflation"),
    "USO":   AssetMeta(ticker="USO", name="United States Oil Fund", asset_type=AssetType.ETF_COMMODITY,
                       sector="Oil ETF",
                       insider_data_reliable=False, fundamentals_applicable=False,
                       insider_note="Commodity ETF — no insider applicable",
                       fundamentals_note="Commodity — no EPS/PE",
                       macro_sensitive=True, macro_driver="WTI crude oil prices, OPEC decisions"),

    # ── ETFs — Volatility ─────────────────────
    "UVXY":  AssetMeta(ticker="UVXY", name="ProShares Ultra VIX ST", asset_type=AssetType.ETF_VOLATILITY,
                       sector="Volatility ETF",
                       insider_data_reliable=False, fundamentals_applicable=False, ml_applicable=False,
                       insider_note="Volatility instrument — not applicable",
                       ml_note="ML trained on equities — output invalid for volatility instruments"),
    "VXX":   AssetMeta(ticker="VXX", name="iPath S&P 500 VIX ST", asset_type=AssetType.ETF_VOLATILITY,
                       sector="Volatility ETF",
                       insider_data_reliable=False, fundamentals_applicable=False, ml_applicable=False,
                       insider_note="Volatility instrument — not applicable",
                       ml_note="ML trained on equities — output invalid for volatility instruments"),
    "VIXY":  AssetMeta(ticker="VIXY", name="ProShares VIX ST Futures", asset_type=AssetType.ETF_VOLATILITY,
                       sector="Volatility ETF",
                       insider_data_reliable=False, fundamentals_applicable=False, ml_applicable=False,
                       insider_note="Volatility instrument — not applicable",
                       ml_note="ML trained on equities — output invalid for volatility instruments"),
}


# ─────────────────────────────────────────────
# CLASSIFIER
# ─────────────────────────────────────────────

def _resolve_asset_meta(
    ticker: str,
    *,
    config: dict | None = None,
    skip_fetch: bool = False,
) -> tuple[AssetMeta | None, bool]:
    """
    Lookup order: curated ASSET_REGISTRY → JSON cache → live profile inference.
    Returns (meta, auto_inferred).
    """
    meta = ASSET_REGISTRY.get(ticker)
    if meta is not None:
        return meta, False

    meta = get_inferred_meta(ticker)
    if meta is not None:
        return meta, True

    if skip_fetch:
        return None, False

    meta = infer_asset_meta_from_ticker(ticker, config)
    if meta is not None:
        try:
            save_inferred_meta(meta)
        except Exception:
            pass
        return meta, True

    return None, False


def classify_asset(
    ticker: str,
    *,
    config: dict | None = None,
    skip_fetch: bool = False,
) -> ClassificationResult:
    """
    Pre-flight asset classification.
    Returns asset type, adjusted weight profile, and pre-flight flags.

    WHERE TO INTEGRATE IN THRIVE ALPHA UI:
    Call this FIRST before any scoring.
    Feed ClassificationResult.weight_profile into the scoring engine.
    Display ClassificationResult.flags as warnings in the ticker card header.
    """
    ticker = ticker.upper().strip()
    meta, auto_inferred = _resolve_asset_meta(ticker, config=config, skip_fetch=skip_fetch)

    if meta is None:
        # Unknown ticker — default to standard equity with warning
        return ClassificationResult(
            ticker=ticker,
            asset_type=AssetType.EQUITY_US,
            name=ticker,
            sector="Unknown",
            weight_profile=WEIGHT_PROFILES[AssetType.EQUITY_US],
            flags=[PreFlightFlag(
                FlagType.WARN,
                f"Unknown ticker '{ticker}' — defaulting to standard equity profile. "
                "Run scripts/scan_asset_registry.py to auto-classify from signal universe.",
            )],
            is_scoreable=True,
            meta=None,
        )

    wp = WEIGHT_PROFILES[meta.asset_type]
    flags: list[PreFlightFlag] = []

    if auto_inferred:
        flags.append(PreFlightFlag(
            FlagType.INFO,
            f"Auto-classified as {wp.label} from company profile ({meta.sector}).",
        ))
    if not meta.insider_data_reliable and meta.insider_note:
        flags.append(PreFlightFlag(FlagType.WARN, meta.insider_note))

    if not meta.fundamentals_applicable and meta.fundamentals_note:
        flags.append(PreFlightFlag(FlagType.WARN, meta.fundamentals_note))

    if not meta.ml_applicable and meta.ml_note:
        flags.append(PreFlightFlag(FlagType.ERROR, meta.ml_note))

    if meta.geopolitical_risk:
        flags.append(PreFlightFlag(
            FlagType.WARN,
            f"Geopolitical risk ({meta.country}): regulatory/delisting risk not captured in model"
        ))

    if meta.macro_sensitive and meta.macro_driver:
        flags.append(PreFlightFlag(
            FlagType.INFO,
            f"Macro-sensitive: primary driver is {meta.macro_driver} — HMM regime may lag"
        ))

    if meta.sentiment_amplified:
        flags.append(PreFlightFlag(
            FlagType.WARN,
            "Sentiment-amplified: options flow may be retail noise, not institutional signal"
        ))

    if wp.scoring_incompatible:
        flags.append(PreFlightFlag(
            FlagType.ERROR,
            "SCORING INCOMPATIBLE: Standard equity model produces misleading outputs for this instrument. Use dedicated volatility model."
        ))

    return ClassificationResult(
        ticker=ticker,
        asset_type=meta.asset_type,
        name=meta.name,
        sector=meta.sector,
        weight_profile=wp,
        flags=flags,
        is_scoreable=not wp.scoring_incompatible,
        meta=meta,
    )


def get_registered_tickers() -> list[str]:
    """Return all tickers in the registry."""
    return list(ASSET_REGISTRY.keys())


def get_tickers_by_type(asset_type: AssetType) -> list[str]:
    """Return all tickers of a specific asset type."""
    return [t for t, m in ASSET_REGISTRY.items() if m.asset_type == asset_type]
