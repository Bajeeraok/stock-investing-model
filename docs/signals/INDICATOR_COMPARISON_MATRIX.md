# Indicator & Signal Comparison Matrix

What we compute vs what external sources provide, and what we compare.

## Our indicators (from `indicators.py` / `run_daily`)

| Indicator | Description | Compared? | Where |
|-----------|-------------|-----------|--------|
| **Close** | Last adjusted close | ✅ | indicator_comparison: Yahoo, Alpha Vantage, Polygon, Finnhub |
| **RSI (14)** | Wilder RSI on close | ✅ | indicator_comparison: Alpha Vantage |
| **MA20 / MA50** | SMA 20/50 on close | ✅ | indicator_comparison: Alpha Vantage SMA(20), SMA(50) |
| **MA200** | SMA 200 on close | ❌ | AV has SMA(200); can add if needed |
| **MACD hist** | MACD(12,26,9) histogram | ✅ | indicator_comparison: Alpha Vantage MACD |
| **Next-day bias** | Bullish/Neutral/Bearish from backtest | ✅ | indicator_validation: Yahoo; indicator_comparison: Finnhub |
| **Composite score / Regime** | Derived from trend+RSI+MACD | ❌ | No direct external equivalent (our composite) |
| **Returns (1m, 3m, 6m)** | Derived from close | ❌ | Would match if close matches; not compared separately |
| **Volume ratio** | Today vol / 20d avg vol | ❌ | Polygon/AV have volume; could add later |
| **Support / Target levels** | From MAs and ATR | ❌ | No like-for-like external |

## External sources and what they provide

| Source | Close | RSI | SMA/MA | MACD | Analyst / Bias | Config key |
|--------|-------|-----|--------|------|----------------|------------|
| **Yahoo (yfinance)** | ✅ (quote) | ❌* | ❌* | ❌* | ✅ recommendation | — |
| **Alpha Vantage** | ✅ GLOBAL_QUOTE | ✅ RSI | ✅ SMA(20/50/200) | ✅ MACD | ❌ (premium) | `data.alpha_vantage_api_key` |
| **Polygon** | ✅ aggs close | ❌ | ❌ | ❌ | ❌ | `data.polygon_api_key` |
| **Finnhub** | ✅ quote | ❌ | ❌ | ❌ | ✅ recommendation | `data.finnhub_apikey` |

\* Can be computed from Yahoo OHLCV in our pipeline; we don’t fetch Yahoo RSI/SMA/MACD from an external “indicator” API.

## Comparison coverage summary

- **Close:** Yahoo, Alpha Vantage, Polygon, Finnhub — margin % vs ours.
- **RSI:** Alpha Vantage only — margin (absolute) vs ours.
- **MA20 / MA50:** Alpha Vantage SMA(20), SMA(50) — margin % vs ours.
- **MACD hist:** Alpha Vantage MACD histogram — margin (absolute) vs ours.
- **Bias / Recommendation:** Yahoo (indicator_validation), Finnhub (indicator_comparison) — aligned/divergent.

## Not compared (by design or limitation)

- **Regime / composite score** — our own composite; no external analogue.
- **Returns** — derived from close; implied by close comparison.
- **Volume** — available from Polygon/AV; can be added as optional comparison.
- **MA200** — AV supports SMA(200); can be added if needed.
- **TipRanks / Benzinga** — not integrated; would require API keys and mapping to our bias.
