"""
Pre-market engine scheduler: runs full engine and writes data/pre_market_latest.json.
Dashboard and GET /api/pre-market read this file.

Cron / Task Scheduler (weekdays 4am–9:30am ET):
  python backend/scripts/pre_market_scheduler.py

  With --force: run outside pre-market hours.
  With --json: output JSON to stdout (for API live fallback).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from signals.premarket_engine import PreMarketEngine, PreMarketReport
except ImportError:
    print("ERROR: signals.premarket_engine not found.", file=sys.stderr)
    sys.exit(1)

try:
    import pytz
    EST = pytz.timezone("America/New_York")
except ImportError:
    EST = None

OUTPUT_FILE = ROOT / "data" / "pre_market_latest.json"


def _category_from_name(name: str) -> str:
    name_lower = name.lower()
    if "futures" in name_lower or "s&p" in name_lower or "nasdaq" in name_lower:
        return "futures"
    if "europe" in name_lower or "asia" in name_lower:
        return "international"
    if "vix" in name_lower:
        return "volatility"
    if "yield" in name_lower or "treasury" in name_lower:
        return "rates"
    if "dxy" in name_lower or "yen" in name_lower or "jpy" in name_lower:
        return "currency"
    if "copper" in name_lower or "gold" in name_lower or "oil" in name_lower or "crude" in name_lower:
        return "commodity"
    if "bitcoin" in name_lower or "ethereum" in name_lower or "btc" in name_lower or "eth" in name_lower:
        return "crypto"
    if any(x in name_lower for x in ["aapl", "msft", "nvda"]):
        return "megacap"
    return "international"


def _derive_rotation_risk(report: PreMarketReport) -> str:
    nasdaq_sig = next((s for s in report.signals if "Nasdaq" in s.name), None)
    sp500_sig = next((s for s in report.signals if "S&P" in s.name), None)
    if nasdaq_sig is None or sp500_sig is None:
        return "Low"
    divergence = abs(nasdaq_sig.score - sp500_sig.score)
    if nasdaq_sig.score < -0.3 and nasdaq_sig.score < sp500_sig.score - 0.2:
        return "High"
    if divergence > 0.3 or report.composite_score < -0.2:
        return "Medium"
    return "Low"


def report_to_dict(report: PreMarketReport) -> dict:
    return {
        "timestamp": report.timestamp.isoformat(),
        "composite_score": report.composite_score,
        "bias": report.bias.value,
        "confidence": report.confidence,
        "minutes_to_open": report.minutes_to_open,
        "top_bullish": report.top_bullish,
        "top_bearish": report.top_bearish,
        "key_risks": report.key_risks,
        "sector_plays": report.suggested_tickers,
        "rotation_risk_premarket": _derive_rotation_risk(report),
        "message": (
            f"Pre-market {report.bias.value} ({report.composite_score:+.2f}) | "
            f"{report.minutes_to_open}m to open"
            + (f" | ↑ {report.top_bullish[0].split(':')[0].strip()}" if report.top_bullish else "")
            + (f" | ↓ {report.top_bearish[0].split(':')[0].strip()}" if report.top_bearish else "")
        ),
        "signals": [
            {
                "name": s.name,
                "category": _category_from_name(s.name),
                "score": s.score,
                "weight": s.weight,
                "raw_value": s.raw_value,
                "direction": s.direction,
                "confidence": s.confidence,
                "note": s.note or "",
            }
            for s in report.signals
            if s.confidence > 0
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Pre-market signal engine scheduler")
    parser.add_argument("--json", action="store_true", help="Output JSON to stdout")
    parser.add_argument("--force", action="store_true", help="Run outside pre-market hours")
    args = parser.parse_args()

    from datetime import datetime
    now = datetime.now(EST) if EST else datetime.utcnow()
    hour, minute = (now.hour, now.minute) if EST else (now.hour, now.minute)
    is_premarket = (hour >= 4 and hour < 9) or (hour == 9 and minute < 30)
    is_weekday = now.weekday() < 5

    if not args.force and (not is_weekday or not is_premarket):
        if not args.json:
            print(f"Skipping: not pre-market hours. Use --force to override.")
        sys.exit(0)

    if not args.json:
        print("Running pre-market engine...")

    engine = PreMarketEngine()
    report = engine.run(verbose=not args.json)
    data = report_to_dict(report)

    if args.json:
        print(json.dumps(data, indent=2))
        return

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(data, indent=2))
    print(f"Saved to {OUTPUT_FILE}")
    print(f"  Bias: {data['bias']}  Score: {data['composite_score']:+.3f}  Signals: {len(data['signals'])}")


if __name__ == "__main__":
    main()
