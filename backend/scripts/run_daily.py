"""
Daily run: fetch watchlist -> compute signals -> print table; optional persistence for alerts.
Run after market close (e.g. cron / Task Scheduler).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

# Add project root so we can import signals
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import yaml
from alerts.notifier import send_alert_digest
from behavior.thesis import load_theses, get_nudge
from behavior.what_changed import what_changed
from opportunity.scanner import run_opportunity_scan
from portfolio.doctor import portfolio_report
from signals.fetcher import fetch_ohlcv_safe, fetch_ohlcv_with_config
from signals.indicators import multi_horizon_scores
from signals.providers import get_next_earnings
from signals.regime import get_regime, get_signal


def load_config() -> dict:
    config_path = ROOT / "config" / "config.yaml"
    if not config_path.exists():
        return {
            "watchlist": ["SPY", "QQQ", "GLD", "SLV", "AAPL", "MSFT"],
            "score": {"buy_min": 70, "sell_max": 30},
            "regime": {"up_min": 60, "down_max": 40},
            "data": {"period": "5y"},
        }
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def load_last_run(path: Path | None = None) -> dict[str, dict] | None:
    """Load previous run: ticker -> {composite_buy, regime}."""
    if path is None:
        path = ROOT / "data" / "last_run.json"
    if not path.exists():
        return None
    try:
        with open(path) as f:
            data = json.load(f)
        return {r["ticker"]: r for r in data.get("run_results", [])}
    except Exception:
        return None


def run_signals(config: dict) -> list[dict]:
    watchlist = config.get("watchlist", [])
    period = config.get("data", {}).get("period", "5y")
    score_cfg = config.get("score", {})
    regime_cfg = config.get("regime", {})
    alert_delta = config.get("alert_score_delta", 15)

    buy_min = score_cfg.get("buy_min", 70)
    sell_max = score_cfg.get("sell_max", 30)
    up_min = regime_cfg.get("up_min", 60)
    down_max = regime_cfg.get("down_max", 40)

    last_run = load_last_run()

    earnings_cfg = config.get("earnings", {}) or {}
    days_warn = earnings_cfg.get("days_warning", 14)
    score_red = earnings_cfg.get("score_reduction", 20)

    results = []
    for ticker in watchlist:
        close = fetch_ohlcv_with_config(ticker, period, config)
        if close is None:
            close = fetch_ohlcv_safe(ticker, period)
        if close is None:
            results.append({
                "ticker": ticker,
                "error": "Insufficient data or fetch failed",
                "close": None,
                "composite_buy": None,
                "regime": None,
                "signal": None,
                "short_term": None,
                "medium_term": None,
                "long_term": None,
                "short_suggestion": None,
                "medium_suggestion": None,
                "long_suggestion": None,
                "story_change": None,
            })
            continue

        sig = multi_horizon_scores(close)
        composite_buy = sig["composite_buy"]
        regime = get_regime(composite_buy, up_min, down_max)
        signal = get_signal(composite_buy, buy_min, sell_max)

        # Earnings: reduce score or flag when within N days
        earnings_note = None
        earnings_info = get_next_earnings(ticker, config)
        if earnings_info and earnings_info.get("days_until") is not None:
            days_until = earnings_info["days_until"]
            if 0 <= days_until <= days_warn:
                earnings_note = f"Earnings in {days_until} days"
                composite_buy = max(0, composite_buy - score_red)
                regime = get_regime(composite_buy, up_min, down_max)
                signal = get_signal(composite_buy, buy_min, sell_max)

        # Story-change detection: regime flip or score drop
        story_change = None
        if last_run and ticker in last_run:
            prev = last_run[ticker]
            prev_regime = prev.get("regime")
            prev_score = prev.get("composite_buy")
            if prev_regime and prev_regime != regime:
                story_change = f"REGIME: {prev_regime} -> {regime}"
            elif prev_score is not None and composite_buy is not None:
                delta = prev_score - composite_buy
                if delta >= alert_delta:
                    story_change = f"SCORE DROP: {prev_score:.0f} -> {composite_buy:.0f} (-{delta:.0f})"

        results.append({
            "ticker": ticker,
            "close": sig["close"],
            "trend_score": sig["trend_score"],
            "rsi": sig["rsi"],
            "ma20": sig.get("ma20"),
            "ma50": sig.get("ma50"),
            "macd_hist": sig.get("macd_hist"),
            "composite_buy": composite_buy,
            "regime": regime,
            "signal": signal,
            "earnings_note": earnings_note,
            "short_term": sig.get("short_term"),
            "medium_term": sig.get("medium_term"),
            "long_term": sig.get("long_term"),
            "short_suggestion": sig.get("short_suggestion"),
            "medium_suggestion": sig.get("medium_suggestion"),
            "long_suggestion": sig.get("long_suggestion"),
            "story_change": story_change,
        })
    return results


def save_last_run(results: list[dict], path: Path | None = None) -> None:
    if path is None:
        path = ROOT / "data" / "last_run.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "run_date": datetime.now().isoformat(),
        "run_results": [
            {
                "ticker": r["ticker"],
                "composite_buy": r.get("composite_buy"),
                "regime": r.get("regime"),
                "rsi": r.get("rsi"),
                "trend_score": r.get("trend_score"),
                "ma20": r.get("ma20"),
                "ma50": r.get("ma50"),
                "macd_hist": r.get("macd_hist"),
            }
            for r in results
        ],
    }
    with open(path, "w") as f:
        json.dump(payload, f, indent=2)


def main() -> None:
    config = load_config()
    results = run_signals(config)

    # Story-change alerts first (trim before it goes too low)
    story_changes = [r for r in results if r.get("story_change")]
    if story_changes:
        print("=" * 60)
        print("STORY CHANGE ALERTS (review these first):")
        print("=" * 60)
        for r in story_changes:
            print(f"  {r['ticker']:6}  {r['story_change']}")
        print()

    # Main signals table
    print("Daily signals (medium-term = main):")
    print("-" * 80)
    for r in results:
        if r.get("error"):
            print(f"  {r['ticker']}: ERROR - {r['error']}")
        else:
            flag = " <-- STORY CHANGE" if r.get("story_change") else ""
            earn = f" [{r['earnings_note']}]" if r.get("earnings_note") else ""
            print(f"  {r['ticker']:6}  close={r['close']:.2f}  med={r['composite_buy']:.1f}  regime={r['regime']:8}  {r['signal']}{earn}{flag}")

    # Multi-horizon suggestions
    print()
    print("Multi-horizon suggestions (short=weeks, med=months, long=1-2yr):")
    print("-" * 80)
    for r in results:
        if r.get("error"):
            continue
        short = r.get("short_suggestion") or "-"
        med = r.get("medium_suggestion") or "-"
        long_s = r.get("long_suggestion") or "-"
        print(f"  {r['ticker']:6}  Short: {short:14}  Medium: {med:14}  Long: {long_s}")

    # Phase 3: Portfolio doctor (full report)
    portfolio = config.get("portfolio", [])
    if isinstance(portfolio, list) and portfolio and isinstance(portfolio[0], dict):
        holdings = portfolio
    else:
        holdings = [{"ticker": t, "quantity": 1} for t in config.get("watchlist", [])]

    report = portfolio_report(
        holdings=holdings,
        results=results,
        watchlist=config.get("watchlist", []),
        score_cfg=config.get("score", {}),
        concentration_threshold_pct=config.get("concentration_alert_pct", 20),
        cash_deploy_min_score=config.get("cash_deploy_min_score", 70),
    )

    print()
    print("=" * 60)
    print("PORTFOLIO HEALTH")
    print("=" * 60)
    print(f"Total value: ${report['total_value']:,.2f}")
    print(f"Average score: {report['avg_score']:.1f}")
    print(f"Regime mix: UP={report['regime_counts']['UP']}  NEUTRAL={report['regime_counts']['NEUTRAL']}  DOWN={report['regime_counts']['DOWN']}")
    if report["largest_position"]:
        lp = report["largest_position"]
        print(f"Largest position: {lp['ticker']} ({lp['pct']:.1f}%, ${lp['value']:,.2f})")
    if report["concentration_alert"]:
        print(f"Concentration alert: {', '.join(report['concentration_alert'])} exceed 20%")

    print()
    print("Per-holding:")
    print("-" * 70)
    for h in sorted(report["per_holding"], key=lambda x: -(x["value"] or 0)):
        val_str = f"${h['value']:,.2f}" if h["value"] else "N/A"
        pct_str = f"{h['pct']:.1f}%" if h["pct"] is not None else "-"
        score_str = f"{h['score']:.1f}" if h["score"] is not None else "-"
        print(f"  {h['ticker']:6}  {val_str:>12}  {pct_str:>6}  score={score_str:>5}  {h['regime'] or '-':8}  {h['suggestion']}")

    # Consider trim
    trim_candidates = [h for h in report["per_holding"] if h["score"] is not None and h["score"] < 40]
    if trim_candidates:
        print()
        print("Consider trim (score < 40, protect gains):")
        for h in sorted(trim_candidates, key=lambda x: x["score"]):
            print(f"  {h['ticker']:6}  score={h['score']:.1f}  regime={h['regime']}  {h['suggestion']}")

    # Cash deployment
    if report["cash_deployment"]:
        print()
        print("Deploy cash (watchlist, not in portfolio, score >= 70):")
        for c in report["cash_deployment"]:
            print(f"  {c['ticker']:6}  score={c['score']:.1f}  regime={c['regime']}")

    # Opportunity scan: long-term growth potential (daily discovery)
    if config.get("run_opportunity_scan", True):
        opp_cfg = config.get("opportunity_criteria", {}) or {}
        universe = config.get("opportunity_universe") or []
        portfolio_tickers = [h.get("ticker") if isinstance(h, dict) else h for h in holdings]
        opportunities = run_opportunity_scan(
            universe=universe if universe else None,
            period=config.get("data", {}).get("period", "5y"),
            min_score=opp_cfg.get("min_score", 70),
            require_regime_up=opp_cfg.get("require_regime_up", True),
            max_rsi=opp_cfg.get("max_rsi", 75),
            require_price_above_ma200=True,
            min_macd_hist=opp_cfg.get("min_macd_hist", 0),
            up_min=config.get("regime", {}).get("up_min", 60),
            down_max=config.get("regime", {}).get("down_max", 40),
            exclude_from_watchlist=portfolio_tickers,
            max_results=opp_cfg.get("max_results", 25),
        )
        print()
        print("=" * 60)
        print("DAILY OPPORTUNITIES (long-term growth potential)")
        print("=" * 60)
        print("Candidates to research - not buy recommendations. Use your judgment.")
        print("-" * 70)
        if opportunities:
            for o in opportunities:
                print(f"  {o['ticker']:6}  close={o['close']:.2f}  score={o['composite_buy']:.1f}  RSI={o['rsi']:.1f}  {o['regime']:8}  {o['reason']}")
        else:
            print("  No tickers passed criteria today. Try relaxing min_score or max_rsi in config.")

    # Phase 5: Thesis check, nudges, what changed
    theses = load_theses() if config.get("run_thesis_check", True) else {}
    last_run = load_last_run()
    if config.get("run_thesis_check", True) and theses:
        print()
        print("=" * 60)
        print("THESIS CHECK")
        print("=" * 60)
        for r in results:
            if r.get("error"):
                continue
            t = theses.get(r["ticker"])
            if not t:
                continue
            nudge = get_nudge(r["ticker"], r.get("regime", ""), r.get("composite_buy"), theses)
            print(f"  {r['ticker']:6}  Why: {t.get('thesis', '-')[:60]}...")
            print(f"         Exit if: {t.get('exit_condition', '-')}")
            if nudge:
                print(f"         -> {nudge}")
            print()

    if config.get("run_what_changed", True) and last_run:
        changed = []
        for r in results:
            if r.get("error"):
                continue
            prev = last_run.get(r["ticker"])
            if not prev:
                continue
            diffs = what_changed(prev, r)
            if diffs:
                changed.append((r["ticker"], diffs))
        if changed:
            print("=" * 60)
            print("WHAT CHANGED (vs last run)")
            print("=" * 60)
            for ticker, diffs in changed[:10]:  # Limit to 10 tickers
                print(f"  {ticker}: {'; '.join(diffs)}")
            print()

    if config.get("show_tooltips", False):
        import yaml as _yaml
        tt_path = ROOT / "config" / "tooltips.yaml"
        if tt_path.exists():
            with open(tt_path, "r") as f:
                tt = _yaml.safe_load(f) or {}
            print("=" * 60)
            print("INDICATOR EXPLANATIONS")
            print("=" * 60)
            for k, v in (tt or {}).items():
                if isinstance(v, str):
                    print(f"  {k}: {v}")
            print()

    # Phase 2: Send alerts (email/Telegram) when story changes
    if story_changes and config.get("alerts"):
        try:
            full_report_lines = [
                f"Portfolio avg: {report['avg_score']:.1f}",
                f"Consider trim: {[h['ticker'] for h in trim_candidates]}",
            ]
            full_report = "\n".join(full_report_lines)
            sent = send_alert_digest(story_changes, config, full_report)
            if sent:
                print("\nAlerts sent (email/Telegram).")
        except Exception as e:
            print(f"\nAlert send failed: {e}")

    # Persist for next-run alerts
    save_last_run(results)
    print("\nSaved to data/last_run.json (story-change alerts on next run).")


if __name__ == "__main__":
    main()
