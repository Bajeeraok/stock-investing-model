"""
Thrive Alpha — Scanner universe + thresholds (Level 2).
Ported from user-provided `alerts-level2` with minimal changes.
"""

from __future__ import annotations

from enum import Enum
from dataclasses import dataclass
from typing import Optional


class AlertType(str, Enum):
    MACRO_RISK_OFF = "MACRO_RISK_OFF"
    MACRO_RISK_ON = "MACRO_RISK_ON"
    ER_LOTTO = "ER_LOTTO"
    ER_IV_CRUSH = "ER_IV_CRUSH"
    COVERED_CALL = "COVERED_CALL"
    CREDIT_SPREAD = "CREDIT_SPREAD"
    MOMENTUM_BREAKOUT = "MOMENTUM_BREAKOUT"
    SUPPORT_BOUNCE = "SUPPORT_BOUNCE"
    KELLY_REDUCTION = "KELLY_REDUCTION"
    OPTIONS_FLOW_SPIKE = "OPTIONS_FLOW_SPIKE"
    REGIME_CHANGE = "REGIME_CHANGE"
    # Retail quick-decision alerts (plain English, action + price + timeline)
    EARNINGS_SOON = "EARNINGS_SOON"
    ENTRY_ZONE_ENTERED = "ENTRY_ZONE_ENTERED"
    STOP_HIT = "STOP_HIT"
    STOP_APPROACHING = "STOP_APPROACHING"
    TARGET_HIT = "TARGET_HIT"
    # Price within ~trim band below target (partial profit / scale out)
    TARGET_APPROACHING = "TARGET_APPROACHING"
    ML_PROB_CROSSED = "ML_PROB_CROSSED"
    # Accumulate track: 3/4 gates + ST verdict supports add (does not replace primary GO)
    SETUP_ALMOST_READY = "SETUP_ALMOST_READY"


class ScanTier(str, Enum):
    TIER1_CORE = "TIER1_CORE"
    TIER2_EARNINGS = "TIER2_EARNINGS"
    TIER3_WATCHLIST = "TIER3_WATCHLIST"
    TIER4_MOMENTUM = "TIER4_MOMENTUM"


class ScanPriority(int, Enum):
    CRITICAL = 1
    HIGH = 2
    MEDIUM = 3
    LOW = 4


@dataclass
class TickerMeta:
    symbol: str
    name: str
    sector: str
    tier: ScanTier
    min_price: float = 5.0
    options_liquid: bool = True
    ttl_hours: Optional[int] = None


TIER1_UNIVERSE: list[TickerMeta] = [
    TickerMeta("AAPL", "Apple", "Technology", ScanTier.TIER1_CORE),
    TickerMeta("MSFT", "Microsoft", "Technology", ScanTier.TIER1_CORE),
    TickerMeta("NVDA", "Nvidia", "Semiconductors", ScanTier.TIER1_CORE),
    TickerMeta("GOOGL", "Alphabet", "Technology", ScanTier.TIER1_CORE),
    TickerMeta("META", "Meta Platforms", "Technology", ScanTier.TIER1_CORE),
    TickerMeta("AMZN", "Amazon", "Consumer/Tech", ScanTier.TIER1_CORE),
    TickerMeta("TSLA", "Tesla", "Automotive/Tech", ScanTier.TIER1_CORE),
    TickerMeta("MSTR", "MicroStrategy", "Crypto/Tech", ScanTier.TIER1_CORE),
    TickerMeta("MARA", "Marathon Digital", "Crypto Mining", ScanTier.TIER1_CORE),
    TickerMeta("RIOT", "Riot Platforms", "Crypto Mining", ScanTier.TIER1_CORE),
    TickerMeta("COIN", "Coinbase", "Crypto/Finance", ScanTier.TIER1_CORE),
    TickerMeta("SMCI", "Super Micro", "Semiconductors", ScanTier.TIER1_CORE),
    TickerMeta("CLSK", "CleanSpark", "Crypto Mining", ScanTier.TIER1_CORE),
    TickerMeta("QQQ", "Nasdaq 100 ETF", "ETF", ScanTier.TIER1_CORE),
    TickerMeta("SPY", "S&P 500 ETF", "ETF", ScanTier.TIER1_CORE),
    TickerMeta("IWM", "Russell 2000 ETF", "ETF", ScanTier.TIER1_CORE),
    TickerMeta("XLK", "Tech Sector ETF", "ETF", ScanTier.TIER1_CORE),
    TickerMeta("ARKK", "ARK Innovation ETF", "ETF", ScanTier.TIER1_CORE),
    TickerMeta("GLD", "Gold ETF", "ETF", ScanTier.TIER1_CORE),
    TickerMeta("AMD", "Advanced Micro Devices", "Semiconductors", ScanTier.TIER1_CORE),
    TickerMeta("AVGO", "Broadcom", "Semiconductors", ScanTier.TIER1_CORE),
    TickerMeta("QCOM", "Qualcomm", "Semiconductors", ScanTier.TIER1_CORE),
    TickerMeta("MU", "Micron Technology", "Semiconductors", ScanTier.TIER1_CORE),
    TickerMeta("TSM", "TSMC", "Semiconductors", ScanTier.TIER1_CORE),
    TickerMeta("CRM", "Salesforce", "SaaS", ScanTier.TIER1_CORE),
    TickerMeta("NOW", "ServiceNow", "SaaS", ScanTier.TIER1_CORE),
    TickerMeta("PANW", "Palo Alto Networks", "Cybersecurity", ScanTier.TIER1_CORE),
    TickerMeta("ZS", "Zscaler", "Cybersecurity", ScanTier.TIER1_CORE),
    TickerMeta("CRWD", "CrowdStrike", "Cybersecurity", ScanTier.TIER1_CORE),
    TickerMeta("SNOW", "Snowflake", "SaaS/Data", ScanTier.TIER1_CORE),
    TickerMeta("PLTR", "Palantir", "AI/Data", ScanTier.TIER1_CORE),
    TickerMeta("DDOG", "Datadog", "SaaS", ScanTier.TIER1_CORE),
    TickerMeta("SHOP", "Shopify", "E-Commerce", ScanTier.TIER1_CORE),
    TickerMeta("NET", "Cloudflare", "Infrastructure", ScanTier.TIER1_CORE),
    TickerMeta("NFLX", "Netflix", "Streaming", ScanTier.TIER1_CORE),
    TickerMeta("UBER", "Uber", "Mobility", ScanTier.TIER1_CORE),
    TickerMeta("ABNB", "Airbnb", "Travel/Tech", ScanTier.TIER1_CORE),
    TickerMeta("JPM", "JPMorgan Chase", "Banking", ScanTier.TIER1_CORE),
    TickerMeta("BAC", "Bank of America", "Banking", ScanTier.TIER1_CORE),
    TickerMeta("GS", "Goldman Sachs", "Banking", ScanTier.TIER1_CORE),
    TickerMeta("V", "Visa", "Payments", ScanTier.TIER1_CORE),
    TickerMeta("PYPL", "PayPal", "Payments", ScanTier.TIER1_CORE),
    TickerMeta("ABBV", "AbbVie", "Healthcare", ScanTier.TIER1_CORE),
    TickerMeta("PFE", "Pfizer", "Healthcare", ScanTier.TIER1_CORE),
    TickerMeta("T", "AT&T", "Telecom", ScanTier.TIER1_CORE),
    TickerMeta("VZ", "Verizon", "Telecom", ScanTier.TIER1_CORE),
    TickerMeta("MO", "Altria", "Consumer", ScanTier.TIER1_CORE),
    TickerMeta("XOM", "ExxonMobil", "Energy", ScanTier.TIER1_CORE),
    TickerMeta("CVX", "Chevron", "Energy", ScanTier.TIER1_CORE),
    TickerMeta("BULL", "Parabolic Industries", "Speculative", ScanTier.TIER1_CORE, min_price=2.0),
    TickerMeta("IONQ", "IonQ", "Quantum", ScanTier.TIER1_CORE, min_price=3.0),
    TickerMeta("RGTI", "Rigetti Computing", "Quantum", ScanTier.TIER1_CORE, min_price=2.0),
    TickerMeta("SOUN", "SoundHound AI", "AI", ScanTier.TIER1_CORE, min_price=2.0),
    TickerMeta("BBAI", "BigBear.ai", "AI", ScanTier.TIER1_CORE, min_price=2.0),
    TickerMeta("RKLB", "Rocket Lab", "Space", ScanTier.TIER1_CORE, min_price=3.0),
]

TIER1_SYMBOLS = {t.symbol for t in TIER1_UNIVERSE}
TICKER_META: dict[str, TickerMeta] = {t.symbol: t for t in TIER1_UNIVERSE}


@dataclass
class SurfacingThreshold:
    alert_type: AlertType
    min_iv_rank: float = 0.0
    max_iv_rank: float = 100.0
    min_flow_ratio: float = 0.0
    max_flow_ratio: float = 99.0
    max_er_days: Optional[int] = None
    min_er_days: Optional[int] = None
    bullish_regime_req: bool = False
    bearish_regime_req: bool = False
    min_regime_conf: float = 0.0
    min_price_change_pct: float = 0.0
    min_price: float = 0.0
    max_atr_pct: float = 99.0
    min_tier: Optional[ScanTier] = None
    surface_to_all: bool = True


SURFACING_THRESHOLDS: dict[AlertType, SurfacingThreshold] = {
    AlertType.ER_LOTTO: SurfacingThreshold(
        alert_type=AlertType.ER_LOTTO,
        min_iv_rank=60,
        min_flow_ratio=1.5,
        max_er_days=3,
        min_er_days=1,
        min_price=5.0,
        surface_to_all=True,
    ),
    AlertType.ER_IV_CRUSH: SurfacingThreshold(
        alert_type=AlertType.ER_IV_CRUSH,
        min_iv_rank=50,
        max_er_days=1,
        surface_to_all=True,
    ),
    AlertType.COVERED_CALL: SurfacingThreshold(
        alert_type=AlertType.COVERED_CALL,
        min_iv_rank=65,
        min_er_days=5,
        max_atr_pct=8.0,
        min_price=10.0,
        surface_to_all=True,
    ),
    AlertType.CREDIT_SPREAD: SurfacingThreshold(
        alert_type=AlertType.CREDIT_SPREAD,
        min_iv_rank=45,
        bullish_regime_req=True,
        min_regime_conf=65.0,
        min_er_days=3,
        surface_to_all=True,
    ),
    AlertType.MOMENTUM_BREAKOUT: SurfacingThreshold(
        alert_type=AlertType.MOMENTUM_BREAKOUT,
        bullish_regime_req=True,
        min_regime_conf=75.0,
        min_price_change_pct=3.0,
        min_flow_ratio=1.2,
        surface_to_all=True,
    ),
    AlertType.SUPPORT_BOUNCE: SurfacingThreshold(
        alert_type=AlertType.SUPPORT_BOUNCE,
        min_iv_rank=20.0,
        min_regime_conf=55.0,
        surface_to_all=False,
    ),
    AlertType.OPTIONS_FLOW_SPIKE: SurfacingThreshold(
        alert_type=AlertType.OPTIONS_FLOW_SPIKE,
        min_flow_ratio=2.5,
        surface_to_all=True,
    ),
    AlertType.REGIME_CHANGE: SurfacingThreshold(
        alert_type=AlertType.REGIME_CHANGE,
        min_regime_conf=80.0,
        surface_to_all=False,
    ),
    AlertType.MACRO_RISK_OFF: SurfacingThreshold(alert_type=AlertType.MACRO_RISK_OFF, surface_to_all=True),
    AlertType.MACRO_RISK_ON: SurfacingThreshold(alert_type=AlertType.MACRO_RISK_ON, surface_to_all=True),
}


RELATED_TICKERS: dict[str, list[str]] = {
    "NVDA": ["AMD", "SMCI", "AVGO", "MU", "TSM"],
    "AMD": ["NVDA", "SMCI", "MU", "AVGO"],
    "MSTR": ["MARA", "RIOT", "COIN", "CLSK"],
    "MARA": ["MSTR", "RIOT", "CLSK", "COIN"],
    "COIN": ["MSTR", "MARA", "RIOT"],
    "QQQ": ["SPY", "NVDA", "AAPL", "MSFT", "META", "GOOGL", "AMZN", "TSLA"],
    "SPY": ["QQQ", "IWM", "XLK"],
    "NOW": ["CRM", "SNOW", "DDOG"],
    "CRWD": ["PANW", "ZS", "S"],
    "PLTR": ["BBAI", "SOUN", "AI"],
}


SECTOR_ETF_MAP: dict[str, str] = {
    "Technology": "XLK",
    "Semiconductors": "SOXX",
    "Healthcare": "XLV",
    "Energy": "XLE",
    "Financials": "XLF",
    "Consumer": "XLY",
    "ETF": "SPY",
    "SaaS": "IGV",
    "Cybersecurity": "CIBR",
}

