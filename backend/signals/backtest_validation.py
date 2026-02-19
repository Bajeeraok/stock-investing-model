"""
Backtest data validation: error band asymmetry, missing 0-30 bucket, score inversion.
Fix 4 from Thrive Alpha Bug Fix Suite.
"""
from __future__ import annotations

import numpy as np


MIN_SAMPLE_SIZE = 10
BUCKETS_EXPECTED = {"70-100", "50-70", "30-50", "0-30"}


def validate_backtest_result(backtest: dict) -> dict:
    """
    Validate a single backtest result (ticker buckets, by_year, etc.).
    Returns { "valid": bool, "issues": list[str], "fixes": list[str], "data_quality_score": int }.
    """
    issues = []
    fixes = []

    buckets = backtest.get("buckets") or {}
    by_year = backtest.get("by_year") or {}

    for year_str, year_data in by_year.items():
        buckets_present = set(year_data.keys())
        missing = BUCKETS_EXPECTED - buckets_present
        for b in missing:
            issues.append(f"Year {year_str}, bucket {b}: No data")
            fixes.append(
                f"Year {year_str}, bucket {b}: If n_signals < {MIN_SAMPLE_SIZE}, "
                "flag as 'Insufficient data' rather than hiding the row."
            )

    # Error band asymmetry (bear vs bull years) — use by_year 3m avg_return_pct
    if by_year:
        try:
            bear_errors = []
            bull_errors = []
            for year_str, year_data in by_year.items():
                m3_70 = year_data.get("70-100", {}).get(3, {})
                m3_0 = year_data.get("0-30", {}).get(3, {})
                avg_3m = m3_70.get("avg_return_pct") or m3_0.get("avg_return_pct")
                moe = m3_70.get("margin_of_error_pct") or 0
                if avg_3m is not None:
                    if avg_3m < 0:
                        bear_errors.append(moe)
                    else:
                        bull_errors.append(moe)
            if bear_errors and bull_errors:
                bear_avg = np.mean(bear_errors)
                bull_avg = np.mean(bull_errors)
                if bull_avg and bear_avg / bull_avg > 1.5:
                    issues.append(
                        f"Error band asymmetry: Bear years ±{bear_avg:.2f}% vs Bull ±{bull_avg:.2f}%"
                    )
                    fixes.append(
                        "Display error bands with color coding (e.g. orange for high variance) "
                        "and tooltip: bear market signals have inherently higher uncertainty."
                    )
        except Exception:
            pass

    # Score inversion: 0-30 bucket beat 70-100 in same year
    for year_str, year_data in by_year.items():
        high = year_data.get("70-100", {}).get(3, {}).get("avg_return_pct")
        low = year_data.get("0-30", {}).get(3, {}).get("avg_return_pct")
        if high is not None and low is not None and low > high:
            issues.append(
                f"Year {year_str}: Score inversion — 0-30 bucket ({low:+.2f}%) > 70-100 ({high:+.2f}%) at 3m."
            )
            fixes.append(
                f"Year {year_str}: Tag as BEAR regime; add visual indicator (e.g. Bear Year) in table."
            )

    score = max(0, 100 - len(issues) * 10)
    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "fixes": fixes,
        "data_quality_score": score,
    }


def compute_error_band_bootstrap(returns: list[float], n_bootstrap: int = 1000) -> dict:
    """
    Bootstrap 90% CI for avg return instead of simple ±std.
    Returns { "mean", "lower", "upper", "std", "method", "n" }.
    """
    if not returns or len(returns) < 3:
        return {"mean": None, "lower": None, "upper": None, "method": "insufficient_data", "n": len(returns or [])}
    arr = np.array(returns)
    boot_means = [
        np.mean(np.random.choice(arr, size=len(arr), replace=True))
        for _ in range(n_bootstrap)
    ]
    lower = np.percentile(boot_means, 5)
    upper = np.percentile(boot_means, 95)
    return {
        "mean": round(float(np.mean(arr)), 2),
        "lower": round(float(lower), 2),
        "upper": round(float(upper), 2),
        "std": round(float(np.std(arr)), 2),
        "method": "bootstrap_90pct_CI",
        "n": len(returns),
    }
