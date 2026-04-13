"""
Cross-asset (DXY, gold, oil) and crypto (BTC, ETH) daily signals.
"""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from signals.fetcher import fetch_ohlcv_safe
from signals.indicators import composite_score
from signals.regime import get_regime, get_signal
from signals.score_interpretation import effective_buy_min


def normalize_vix_close_price(close: float | None) -> float | None:
    """
    VIX index is almost always ~8–90. Some feeds occasionally return hundredfold values
    (e.g. 2181 instead of 21.81). Normalize for display and regime logic.
    """
    if close is None:
        return None
    try:
        x = float(close)
    except (TypeError, ValueError):
        return None
    # Hundredfold bug (e.g. 2181); real VIX prints are almost always < 120.
    if x > 200:
        x = x / 100.0
    return x


def run_crypto_signals(tickers: list[str], config: dict) -> list[dict]:
    """Run signals for crypto tickers (BTC-USD, ETH-USD). Same logic as equities."""
    period = config.get("data", {}).get("period", "2y") or "2y"
    score_cfg = config.get("score", {})
    regime_cfg = config.get("regime", {})
    sell_max = score_cfg.get("sell_max", 30)
    up_min = regime_cfg.get("up_min", 60)
    down_max = regime_cfg.get("down_max", 40)

    results = []
    for ticker in tickers:
        close = fetch_ohlcv_safe(ticker, period)
        if close is None or len(close) < 50:
            results.append({
                "ticker": ticker,
                "close": None,
                "composite_buy": None,
                "regime": None,
                "signal": None,
                "rsi": None,
                "error": "Insufficient data",
            })
            continue
        sig = composite_score(close)
        regime = get_regime(sig["composite_buy"], up_min, down_max)
        buy_min = effective_buy_min(ticker, score_cfg)
        signal = get_signal(sig["composite_buy"], buy_min, sell_max)
        results.append({
            "ticker": ticker,
            "close": sig["close"],
            "composite_buy": sig["composite_buy"],
            "regime": regime,
            "signal": signal,
            "rsi": sig.get("rsi"),
        })
    return results


def run_cross_asset_daily(tickers: list[str]) -> list[dict]:
    """Fetch DXY, GLD, USO, VIX and return daily % change vs prior close."""
    labels = {
        "DX-Y.NYB": "DXY",
        "GLD": "Gold",
        "USO": "Oil",
        "UNG": "Nat gas",
        "^VIX": "VIX",
        "10Y": "10Y Treasury",
    }
    results = []
    for ticker in tickers:
        close = fetch_ohlcv_safe(ticker, "1mo")
        if close is None or len(close) < 2:
            results.append({"ticker": ticker, "pct_change": None, "close": None, "error": "No data"})
            continue
        last = float(close.iloc[-1])
        prev = float(close.iloc[-2])
        pct = round(100 * (last - prev) / prev, 2) if prev and prev > 0 else None
        label = labels.get(ticker, ticker)
        results.append({"ticker": ticker, "label": label, "close": last, "pct_change": pct})
    return results


def compute_cross_asset_guidelines(
    cross_asset: list[dict],
    economic_calendar: list[dict],
    real_yield: float | None = None,
    inflation_exp: float | None = None,
    cot_extremes: list[dict] | None = None,
) -> list[dict]:
    """
    Generate actionable guidelines from cross-asset + calendar + optional FRED macro + CFTC COT.
    Returns list of {text, type: "caution"|"info"|"risk"}.
    real_yield: 10Y nominal - inflation expectations (from FRED); headwind for gold/growth when high.
    inflation_exp: 10Y breakeven inflation (T10YIE); optional context.
    cot_extremes: from cot_client.get_cot_extremes_for_guidelines(); spec positioning extreme = reversal risk.
    """
    guidelines = []
    by_label = {a.get("label", a.get("ticker", "")): a for a in cross_asset if isinstance(a, dict)}

    dxy = by_label.get("DXY") or by_label.get("DX-Y.NYB")
    gld = by_label.get("Gold") or by_label.get("GLD")
    slv = by_label.get("SLV")
    vix = by_label.get("VIX")
    rate_10y = by_label.get("10Y Treasury") or by_label.get("10Y")

    # CFTC COT: speculative positioning extreme = reversal risk (GLD/SLV/oil)
    for item in (cot_extremes or []):
        if not isinstance(item, dict) or not item.get("extreme"):
            continue
        label = item.get("label", "Commodity")
        extreme = item.get("extreme")
        if extreme == "long":
            guidelines.append({
                "text": f"Spec positioning ({label}): Speculators are very long futures; historically that's often been a setup for a pullback – reversal risk. Consider not adding size.",
                "type": "caution",
            })
        else:
            guidelines.append({
                "text": f"Spec positioning ({label}): Speculators are very short futures; historically that's often been a setup for a squeeze – reversal risk. Watch for sharp moves up.",
                "type": "caution",
            })

    # Real yield (10Y - inflation exp) – headwind for gold/growth when high
    if real_yield is not None:
        if real_yield > 2.0:
            guidelines.append({
                "text": f"Real yields elevated ({real_yield:.1f}%): Real cost of capital is high – headwind for gold and growth stocks. Gold and long-duration growth often underperform when real yields rise.",
                "type": "caution",
            })
        elif real_yield > 1.5:
            guidelines.append({
                "text": f"Real yields at {real_yield:.1f}%: Real cost of capital is in a range where gold and growth are sensitive; watch for impact if real yields move higher.",
                "type": "info",
            })

    # DXY + real yield → gold pressure (combined rule)
    dxy_pct = (dxy or {}).get("pct_change")
    if dxy_pct is not None and real_yield is not None:
        if dxy_pct > 0.3 and real_yield > 1.5:
            guidelines.append({
                "text": f"DXY strength (+{dxy_pct:.1f}%) and real yields ({real_yield:.1f}%): Dollar strength plus higher real rates typically put gold under pressure.",
                "type": "caution",
            })

    # DXY up + GLD down = dollar strength pressure
    if dxy and gld:
        dxy_pct = dxy.get("pct_change")
        gld_pct = gld.get("pct_change")
        if dxy_pct is not None and gld_pct is not None:
            if dxy_pct > 0.3 and gld_pct < -0.3:
                guidelines.append({
                    "text": f"Dollar strength (DXY +{dxy_pct:.1f}%) – metals under pressure (GLD {gld_pct:.1f}%)",
                    "type": "caution",
                })

    # VIX spike + GLD down = risk-off
    if vix and gld:
        vix_val = normalize_vix_close_price(vix.get("close"))
        gld_pct = gld.get("pct_change")
        if vix_val is not None and gld_pct is not None and gld_pct < -0.5:
            if vix_val > 20:
                guidelines.append({
                    "text": f"Risk-off: VIX elevated ({vix_val:.2f}) + metals down – reduce size, tighten stops",
                    "type": "risk",
                })

    # 10Y rate context (real yield proxy – would need inflation for true real yield)
    if rate_10y and rate_10y.get("close") is not None:
        r = float(rate_10y["close"])
        if r > 4.5:
            guidelines.append({
                "text": f"10Y Treasury at {r:.1f}% – higher rates = headwind for gold/growth stocks",
                "type": "info",
            })

    # Heavy macro week (CPI, FOMC in next 7 days)
    heavy_keywords = ("cpi", "ppi", "nfp", "fomc", "fed", "ecb", "jobs", "inflation")
    heavy_events = []
    for e in (economic_calendar or [])[:50]:
        if not isinstance(e, dict):
            continue
        name = (e.get("name") or e.get("event") or e.get("title") or "").lower()
        country = (e.get("country") or "").lower()
        if any(kw in name or kw in country for kw in heavy_keywords):
            heavy_events.append(e.get("name") or e.get("event") or str(e)[:50])
    if len(heavy_events) >= 2:
        guidelines.append({
            "text": "Heavy macro week (CPI, FOMC, etc.) – consider reducing size, tightening stops",
            "type": "caution",
        })
    elif len(heavy_events) == 1:
        guidelines.append({
            "text": f"Macro event this week: {heavy_events[0][:60]} – expect volatility",
            "type": "info",
        })

    return guidelines
