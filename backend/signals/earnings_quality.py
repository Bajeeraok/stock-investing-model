"""
Earnings quality heuristics: cash vs accruals, margin vs revenue growth, estimate revisions (FMP).
Not a formal earnings-quality model — flags deterioration early.
"""
from __future__ import annotations

import logging
from typing import Any

import requests

from signals.fmp_client import BASE_V3, fetch_analyst_estimates_quarterly, get_api_key

logger = logging.getLogger(__name__)


def _income_and_cf(config: dict, ticker: str) -> tuple[list[dict] | None, list[dict] | None, str | None]:
    api_key = get_api_key(config)
    if not api_key:
        return None, None, "No FMP API key"
    sym = (ticker or "").upper().split("-")[0]
    params = {"period": "quarter", "limit": 8, "apikey": api_key}
    try:
        ri = requests.get(f"{BASE_V3}/income-statement/{sym}", params=params, timeout=15)
        rc = requests.get(f"{BASE_V3}/cash-flow-statement/{sym}", params=params, timeout=15)
        ri.raise_for_status()
        rc.raise_for_status()
        inc = ri.json()
        cf = rc.json()
    except Exception as e:
        return None, None, str(e)
    if isinstance(inc, list) and isinstance(cf, list):
        return [r for r in inc if isinstance(r, dict)], [r for r in cf if isinstance(r, dict)], None
    return None, None, "No statements"


def _op_margin(row: dict) -> float | None:
    oi = row.get("operatingIncome")
    rev = row.get("revenue")
    if oi is None or not rev:
        return None
    try:
        return float(oi) / float(rev) if float(rev) != 0 else None
    except (TypeError, ValueError):
        return None


def analyze_earnings_quality(config: dict, ticker: str) -> dict[str, Any]:
    income, cashflow, err = _income_and_cf(config, ticker)
    flags: list[str] = []
    score = 100.0

    if not income or not cashflow:
        return {
            "quality_score": 50,
            "grade": "C",
            "flags": [err or "No statement data"],
            "error": err,
        }

    n = min(4, len(income), len(cashflow))
    for i in range(n):
        ni = income[i].get("netIncome")
        ocf = cashflow[i].get("operatingCashFlow") if i < len(cashflow) else None
        try:
            ni_f = float(ni) if ni is not None else None
            ocf_f = float(ocf) if ocf is not None else None
        except (TypeError, ValueError):
            continue
        if ni_f and ni_f > 0 and ocf_f and ocf_f > 0:
            ratio = ocf_f / ni_f
            if ratio < 0.70:
                flags.append(
                    f"Q{i+1}: OCF/NI {ratio:.2f} — possible accrual-heavy earnings"
                )
                score -= 10.0
        if i > 0:
            curr_rev = income[i].get("revenue")
            prev_rev = income[i - 1].get("revenue")
            try:
                cr = float(curr_rev) if curr_rev is not None else 0.0
                pr = float(prev_rev) if prev_rev is not None else 0.0
            except (TypeError, ValueError):
                cr, pr = 0.0, 0.0
            if pr != 0:
                rev_growth = (cr - pr) / abs(pr)
            else:
                rev_growth = 0.0
            cm = _op_margin(income[i])
            pm = _op_margin(income[i - 1])
            if cm is not None and pm is not None and rev_growth > 0.10 and cm < pm - 0.02:
                flags.append(
                    f"Q{i+1}: Revenue growing but operating margin compressing"
                )
                score -= 8.0

    est_rows, est_err = fetch_analyst_estimates_quarterly(config, ticker, limit=4)
    if est_err:
        logger.debug("analyst quarterly estimates: %s", est_err)
    if est_rows and len(est_rows) >= 2:
        def _eps(r: dict) -> float | None:
            for k in ("estimatedEpsAvg", "epsEstimate", "estimatedEps"):
                v = r.get(k)
                if v is not None:
                    try:
                        return float(v)
                    except (TypeError, ValueError):
                        pass
            return None

        curr_est = _eps(est_rows[0])
        prev_est = _eps(est_rows[1])
        if curr_est is not None and prev_est and prev_est != 0:
            revision = (curr_est - prev_est) / abs(prev_est)
            if revision < -0.05:
                flags.append(f"EPS consensus revised down {revision:.1%} vs prior quarter row")
                score -= 15.0
            elif revision > 0.05:
                score += 10.0

    score = max(0.0, min(100.0, score))
    grade = "A" if score >= 85 else "B" if score >= 70 else "C" if score >= 55 else "D"
    return {
        "quality_score": round(score, 1),
        "flags": flags,
        "grade": grade,
    }
