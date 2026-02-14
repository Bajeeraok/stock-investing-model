"""
Price target accuracy: compare model target levels per ticker vs today's close.
Computes margin of error and suggests whether to tweak the model (e.g. ATR in target_bands).

Run from backend:  cd backend && python scripts/accuracy_price_targets.py

  Same-day:  python scripts/accuracy_price_targets.py
  Forward:   python scripts/accuracy_price_targets.py --forward
             (yesterday's EOD targets vs today's close; requires data/eod/YYYY-MM-DD.json)

Interpreting err% and MAPE (thresholds in config.yaml under accuracy:):
  - ST target err% / Support err%: per-ticker |close - level|/close. Acceptable <= 5%; >10% consider tweak.
  - MAPE: mean absolute % error across tickers for that level. Acceptable <= 5-8%; ST MAPE > 8% → consider ATR tweak in target_bands.py.
  - See config.accuracy.notes for full interpretation guide.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config_loader import load_config
from scripts.run_daily import run_signals, load_eod_snapshot


# Level names and whether "close near this" is good (support/buy = close at or above; target = close at or near)
LEVELS = [
    ("st_target_high", "Short-term target (st_band high)", True),   # close ≈ target is good
    ("st_stop_low", "Short-term stop (st_band low)", True),          # close above stop is good
    ("support_level", "Support (MA20)", True),
    ("suggested_buy_price", "Suggested buy (MA50/200)", True),
    ("mt_target_high", "Medium-term band high", True),
    ("mt_stop_low", "Medium-term band low", True),
]


def _get_level_value(row: dict, key: str) -> float | None:
    if key == "st_target_high":
        band = row.get("st_band")
        return float(band["high"]) if isinstance(band, dict) and band.get("high") is not None else None
    if key == "st_stop_low":
        band = row.get("st_band")
        return float(band["low"]) if isinstance(band, dict) and band.get("low") is not None else None
    if key == "mt_target_high":
        band = row.get("mt_band")
        return float(band["high"]) if isinstance(band, dict) and band.get("high") is not None else None
    if key == "mt_stop_low":
        band = row.get("mt_band")
        return float(band["low"]) if isinstance(band, dict) and band.get("low") is not None else None
    if key in ("support_level", "suggested_buy_price"):
        v = row.get(key)
        return float(v) if v is not None else None
    return None


def compute_accuracy(results: list[dict]) -> tuple[list[dict], dict]:
    """
    For each ticker, compare close to each target level; compute error and pct error.
    Returns (per_ticker_rows, summary_by_level).
    """
    per_ticker = []
    by_level: dict[str, list[float]] = {key: [] for key, _label, _ in LEVELS}

    for r in results:
        if r.get("error") or r.get("close") is None:
            continue
        close = float(r["close"])
        row = {"ticker": r["ticker"], "close": close}
        for key, label, _ in LEVELS:
            level_val = _get_level_value(r, key)
            if level_val is None:
                row[key] = None
                row[f"{key}_pct_err"] = None
                row[f"{key}_abs_pct"] = None
                continue
            err = close - level_val
            pct_err = 100 * err / close if close and close != 0 else None
            abs_pct = abs(pct_err) if pct_err is not None else None
            row[key] = round(level_val, 2)
            row[f"{key}_pct_err"] = round(pct_err, 2) if pct_err is not None else None
            row[f"{key}_abs_pct"] = round(abs_pct, 2) if abs_pct is not None else None
            if abs_pct is not None:
                by_level[key].append(abs_pct)
        per_ticker.append(row)

    summary = {}
    for key, label, _ in LEVELS:
        vals = by_level[key]
        if not vals:
            summary[key] = {"label": label, "count": 0, "mape": None, "within_1pct": 0, "within_2pct": 0, "within_5pct": 0}
            continue
        n = len(vals)
        mape = round(sum(vals) / n, 2)
        within_1 = sum(1 for v in vals if v <= 1)
        within_2 = sum(1 for v in vals if v <= 2)
        within_5 = sum(1 for v in vals if v <= 5)
        summary[key] = {
            "label": label,
            "count": n,
            "mape": mape,
            "within_1pct": within_1,
            "within_2pct": within_2,
            "within_5pct": within_5,
        }
    return per_ticker, summary


def run_accuracy_and_save(results: list[dict], config: dict, out_dir: Path | None = None) -> Path | None:
    """
    Compute price-target accuracy from signal results and save to data/accuracy_price_targets.json.
    Call this after run_signals() (e.g. from dashboard or run_daily) so the report is always up to date.
    Returns path to written file or None on failure.
    """
    try:
        per_ticker, summary = compute_accuracy(results)
        recs = recommend_tweaks(summary, config)
        out_dir = out_dir or ROOT / "data"
        out_dir.mkdir(parents=True, exist_ok=True)
        report = {
            "as_of": datetime.now().isoformat(),
            "per_ticker": per_ticker,
            "summary": {
                k: {"label": v["label"], "count": v["count"], "mape": v["mape"], "within_1pct": v["within_1pct"], "within_2pct": v["within_2pct"], "within_5pct": v["within_5pct"]}
                for k, v in summary.items()
            },
            "recommendations": recs,
        }
        report_path = out_dir / "accuracy_price_targets.json"
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2)
        return report_path
    except Exception:
        return None


def recommend_tweaks(summary: dict, config: dict) -> list[str]:
    """Suggest model tweaks based on margin of error. Thresholds from config.accuracy (see config.yaml)."""
    recommendations = []
    acc = (config or {}).get("accuracy") or {}
    st_mape_tweak = acc.get("st_target_mape_tweak_above", 8)
    support_mape_tweak = acc.get("support_mape_tweak_above", 15)

    st = summary.get("st_target_high", {})
    if st.get("mape") is not None:
        if st["mape"] > st_mape_tweak:
            recommendations.append(
                f"Short-term target (st_band high) has high error (MAPE > {st_mape_tweak}%). Consider adjusting "
                "ATR multiplier or horizon in backend/signals/target_bands.py (e.g. 1.5*ATR vs 1.0*ATR)."
            )
        elif st["mape"] < 1.5 and st.get("within_1pct", 0) == st.get("count", 0):
            recommendations.append(
                "Short-term target is very accurate across tickers. No change needed for ST bands."
            )
    supp = summary.get("support_level", {})
    if supp.get("mape") is not None and supp["mape"] > support_mape_tweak:
        recommendations.append(
            "Support (MA20) is far from close on average. MA20 is lagging; this is expected in fast moves. "
            "Consider using MA20 only as 'watch level' not as target."
        )
    return recommendations


def _list_eod_dates() -> list[str]:
    """Return sorted list of EOD snapshot dates (YYYY-MM-DD)."""
    eod_dir = ROOT / "data" / "eod"
    if not eod_dir.exists():
        return []
    dates = []
    for p in eod_dir.glob("*.json"):
        try:
            d = datetime.strptime(p.stem, "%Y-%m-%d").date()
            dates.append(d.strftime("%Y-%m-%d"))
        except ValueError:
            pass
    return sorted(dates) if dates else []


def run_forward_accuracy(eod_date: str | None = None) -> tuple[list[dict], dict, str]:
    """
    Compare prior EOD snapshot's target levels to today's close (forward accuracy).
    Returns (per_ticker_rows, summary_by_level, eod_date_used).
    """
    dates = _list_eod_dates()
    if not dates:
        return [], {}, ""
    use_date = eod_date or dates[-1]
    prior = load_eod_snapshot(use_date)
    if not prior:
        return [], {}, use_date
    config = load_config()
    results = run_signals(config)
    current_by_ticker = {r["ticker"]: r for r in results if not r.get("error") and r.get("close") is not None}

    per_ticker = []
    by_level: dict[str, list[float]] = {key: [] for key, _label, _ in LEVELS}

    for ticker, prev_row in prior.items():
        curr = current_by_ticker.get(ticker)
        if curr is None:
            continue
        close_today = float(curr["close"])
        row = {"ticker": ticker, "prior_date": use_date, "close_today": close_today}
        for key, label, _ in LEVELS:
            level_val = _get_level_value(prev_row, key)
            if level_val is None:
                row[key] = None
                row[f"{key}_pct_err"] = None
                row[f"{key}_abs_pct"] = None
                continue
            err = close_today - level_val
            pct_err = 100 * err / close_today if close_today and close_today != 0 else None
            abs_pct = abs(pct_err) if pct_err is not None else None
            row[key] = round(level_val, 2)
            row[f"{key}_pct_err"] = round(pct_err, 2) if pct_err is not None else None
            row[f"{key}_abs_pct"] = round(abs_pct, 2) if abs_pct is not None else None
            if abs_pct is not None:
                by_level[key].append(abs_pct)
        per_ticker.append(row)

    summary = {}
    for key, label, _ in LEVELS:
        vals = by_level[key]
        if not vals:
            summary[key] = {"label": label, "count": 0, "mape": None, "within_1pct": 0, "within_2pct": 0, "within_5pct": 0}
            continue
        n = len(vals)
        summary[key] = {
            "label": label,
            "count": n,
            "mape": round(sum(vals) / n, 2),
            "within_1pct": sum(1 for v in vals if v <= 1),
            "within_2pct": sum(1 for v in vals if v <= 2),
            "within_5pct": sum(1 for v in vals if v <= 5),
        }
    return per_ticker, summary, use_date


def main() -> None:
    parser = argparse.ArgumentParser(description="Price target accuracy vs close (same-day or forward).")
    parser.add_argument("--forward", action="store_true", help="Forward accuracy: prior EOD targets vs today close")
    parser.add_argument("--eod-date", type=str, default=None, help="EOD snapshot date YYYY-MM-DD (default: latest)")
    args = parser.parse_args()

    if args.forward:
        print("Forward accuracy: prior EOD targets vs today's close")
        print("Running signals for current close...")
        per_ticker, summary, eod_date = run_forward_accuracy(args.eod_date)
        if not eod_date or not per_ticker:
            print("No EOD snapshot found or no matching tickers. Run daily first to save EOD snapshots.")
            return
        print(f"Prior EOD date: {eod_date}")
        print()
        print("-" * 80)
        print("Per-ticker: today close vs prior short-term target and support")
        print("-" * 80)
        print(f"{'Ticker':<8} {'Close today':>12} {'Prior ST target':>14} {'Prior support':>14}  |  ST target abs%err")
        print("-" * 80)
        for row in per_ticker:
            t = row["ticker"]
            c = row["close_today"]
            st_high = row.get("st_target_high")
            supp = row.get("support_level")
            st_abs = row.get("st_target_high_abs_pct")
            st_str = f"{st_high:.2f}" if st_high is not None else "-"
            supp_str = f"{supp:.2f}" if supp is not None else "-"
            st_abs_str = f"{st_abs:.1f}%" if st_abs is not None else "-"
            print(f"{t:<8} {c:>12.2f} {st_str:>14} {supp_str:>14}  |  {st_abs_str:>12}")
        print()
        print("Margin of error (prior targets vs today close):")
        for key, _label, _ in LEVELS:
            s = summary.get(key, {})
            if s.get("count", 0) == 0:
                continue
            print(f"  {s['label']}: count={s['count']}, MAPE={s.get('mape')}%, within 1/2/5% = {s.get('within_1pct')}/{s.get('within_2pct')}/{s.get('within_5pct')}")
        out_path = ROOT / "data" / "accuracy_forward.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            json.dump({
                "as_of": datetime.now().isoformat(),
                "prior_eod_date": eod_date,
                "per_ticker": per_ticker,
                "summary": summary,
            }, f, indent=2)
        print(f"\nSaved to {out_path}")
        return

    # Same-day accuracy (default)
    config = load_config()
    print("Running signals for watchlist...")
    results = run_signals(config)
    per_ticker, summary = compute_accuracy(results)

    print()
    print("=" * 80)
    print("PRICE TARGET ACCURACY vs TODAY'S CLOSE")
    print("=" * 80)
    print("Close = latest close from data. Levels = model outputs (st_band, support, suggested_buy, mt_band).")
    print("Pct error = 100 * (close - level) / close. Positive = close above level.")
    acc = config.get("accuracy") or {}
    st_ok = acc.get("st_target_err_acceptable_pct", 5)
    mape_tweak = acc.get("st_target_mape_tweak_above", 8)
    print(f"Acceptable (no tweak): ST target err <= {st_ok}% per ticker, MAPE <= 5-8%. Consider tweak if ST MAPE > {mape_tweak}% (config.accuracy).")
    print()

    print("-" * 80)
    print("Per-ticker: close vs short-term target and support")
    print("-" * 80)
    print(f"{'Ticker':<8} {'Close':>10} {'ST target':>10} {'Support':>10} {'Buy@':>10}  |  ST target abs%err  Support abs%err")
    print("-" * 80)
    for row in per_ticker:
        t = row["ticker"]
        c = row["close"]
        st_high = row.get("st_target_high")
        supp = row.get("support_level")
        buy = row.get("suggested_buy_price")
        st_abs = row.get("st_target_high_abs_pct")
        supp_abs = row.get("support_level_abs_pct")
        st_str = f"{st_high:.2f}" if st_high is not None else "-"
        supp_str = f"{supp:.2f}" if supp is not None else "-"
        buy_str = f"{buy:.2f}" if buy is not None else "-"
        st_abs_str = f"{st_abs:.1f}%" if st_abs is not None else "-"
        supp_abs_str = f"{supp_abs:.1f}%" if supp_abs is not None else "-"
        print(f"{t:<8} {c:>10.2f} {st_str:>10} {supp_str:>10} {buy_str:>10}  |  {st_abs_str:>12}  {supp_abs_str:>12}")
    print()

    print("-" * 80)
    print("Margin of error by level (mean absolute % error vs close)")
    print("-" * 80)
    print(f"{'Level':<32} {'Count':>6} {'MAPE %':>8}  Within 1%  2%  5%")
    print("-" * 80)
    for key, _label, _ in LEVELS:
        s = summary.get(key, {})
        label = s.get("label", key)
        n = s.get("count", 0)
        mape = s.get("mape")
        w1 = s.get("within_1pct", 0)
        w2 = s.get("within_2pct", 0)
        w5 = s.get("within_5pct", 0)
        mape_str = f"{mape:.1f}%" if mape is not None else "-"
        print(f"{label:<32} {n:>6} {mape_str:>8}  {w1:>4}  {w2:>4}  {w5:>4}")
    print()

    recs = recommend_tweaks(summary, config)
    if recs:
        print("Recommendations (tweak model?):")
        for r in recs:
            print(f"  • {r}")
    else:
        print("No strong tweak recommended; error bands are in a reasonable range.")
    print()

    out_dir = ROOT / "data"
    out_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "as_of": datetime.now().isoformat(),
        "per_ticker": per_ticker,
        "summary": {
            k: {"label": v["label"], "count": v["count"], "mape": v["mape"], "within_1pct": v["within_1pct"], "within_2pct": v["within_2pct"], "within_5pct": v["within_5pct"]}
            for k, v in summary.items()
        },
        "recommendations": recs,
    }
    report_path = out_dir / "accuracy_price_targets.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"Report saved to {report_path}")
