"""Tests for profile-based asset registry inference."""

from signals.pre_flight.asset_registry_infer import infer_asset_meta
from signals.pre_flight.constants import AssetType
from signals.pre_flight.asset_classifier import classify_asset, ASSET_REGISTRY
from signals.pre_flight.asset_registry_cache import save_inferred_meta


def test_bac_inferred_as_us_equity_with_macro():
    profile = {
        "companyName": "Bank of America Corporation",
        "sector": "Financial Services",
        "industry": "Banks - Diversified",
        "beta": 1.35,
        "mktCap": 280_000_000_000,
        "country": "US",
    }
    meta = infer_asset_meta("BAC", profile)
    assert meta is not None
    assert meta.asset_type == AssetType.EQUITY_US
    assert meta.sector == "Financials"
    assert meta.macro_sensitive is True
    assert meta.macro_driver is not None


def test_gld_inferred_as_commodity_etf():
    profile = {
        "companyName": "SPDR Gold Shares",
        "sector": "ETF",
        "isEtf": True,
        "country": "US",
    }
    meta = infer_asset_meta("GLD", profile)
    assert meta is not None
    assert meta.asset_type == AssetType.ETF_COMMODITY
    assert meta.fundamentals_applicable is False


def test_baba_inferred_as_adr():
    profile = {
        "companyName": "Alibaba Group Holding Limited",
        "sector": "Consumer Cyclical",
        "beta": 0.9,
        "country": "CN",
        "exchangeShortName": "NYSE",
    }
    meta = infer_asset_meta("BABA", profile)
    assert meta is not None
    assert meta.asset_type == AssetType.EQUITY_ADR
    assert meta.geopolitical_risk is True


def test_high_beta_inferred_speculative():
    profile = {
        "companyName": "Example Growth Co",
        "sector": "Technology",
        "beta": 2.1,
        "mktCap": 8_000_000_000,
        "country": "US",
    }
    meta = infer_asset_meta("XYZ", profile)
    assert meta.asset_type == AssetType.EQUITY_SPECULATIVE
    assert meta.sentiment_amplified is True


def test_defensive_staples():
    profile = {
        "companyName": "Coca-Cola",
        "sector": "Consumer Defensive",
        "beta": 0.55,
        "country": "US",
    }
    meta = infer_asset_meta("KO2", profile)
    assert meta.asset_type == AssetType.EQUITY_DEFENSIVE


def test_classify_bac_from_cache():
    """After cache seed, BAC should not warn as unknown."""
    from signals.pre_flight.models import AssetMeta

    save_inferred_meta(
        AssetMeta(
            ticker="BAC",
            name="Bank of America Corporation",
            asset_type=AssetType.EQUITY_US,
            sector="Financials",
            beta=1.35,
            macro_sensitive=True,
            macro_driver="Interest rates, credit spreads",
        )
    )
    result = classify_asset("BAC", skip_fetch=True)
    assert result.meta is not None
    assert result.meta.ticker == "BAC"
    assert result.asset_type == AssetType.EQUITY_US
    assert not any("Unknown ticker" in f.message for f in result.flags)
    # cleanup not required — test file cache is ok


def test_registry_tickers_still_curated():
    assert "NVDA" in ASSET_REGISTRY
    result = classify_asset("NVDA", skip_fetch=True)
    assert result.meta is not None
    assert not any("Auto-classified" in f.message for f in result.flags)
