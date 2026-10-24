"""
Earnings quality heuristics: cash vs accruals, margin vs revenue growth, estimate revisions (FMP).
Not a formal earnings-quality model — flags deterioration early.
"""
from __future__ import annotations

import logging
from typing import Any

from signals.fmp_client import BASE_V3, fetch_analyst_estimates_quarterly, get_api_key
from signals.http_session import get_requests_session

logger = logging.getLogger(__name__)


def _income_and_cf(config: dict, ticker: str) -> tuple[list[dict] | None, list[dict] | None, str | None]:
    api_key = get_api_key(config)
    if not api_key:
        return None, None, "No FMP API key"
    sym = (ticker or "").upper().split("-")[0]
    params = {"period": "quarter", "limit": 8, "apikey": api_key}
    try:
        session = get_requests_session()
        ri = session.get(f"{BASE_V3}/income-statement/{sym}", params=params, timeout=15)
        rc = session.get(f"{BASE_V3}/cash-flow-statement/{sym}", params=params, timeout=15)
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


def _est_eps(row: dict) -> float | None:
    for k in ("estimatedEpsAvg", "epsEstimate", "estimatedEps"):
        v = row.get(k)
        if v is not None:
            try:
                return float(v)
            except (TypeError, ValueError):
                pass
    return None


def analyst_revision_breadth(config: dict, ticker: str) -> dict[str, Any] | None:
    """Revision-breadth metrics from the quarterly consensus rows
    (fmp_client.fetch_analyst_estimates_quarterly — rows newest-first, ~91d apart).

    Returns:
      revisions_30d   — net up/down count across the most recent QoQ estimate
                        transitions (#up − #down; roughly the last ~90d window
                        spanned by the rows available)
      est_drift_pct   — % drift of the latest consensus vs the ~90d-ago row
      breadth_score   — 0-1 composite for scoring layers (0.5 = neutral)
      direction       — "rising" | "falling" | "flat" | "mixed"
      n_rows          — rows used
    or None when the endpoint has no data / no key.
    """
    est_rows, err = fetch_analyst_estimates_quarterly(config, ticker, limit=8)
    if err:
        logger.debug("analyst quarterly estimates (%s): %s", ticker, err)
    if not est_rows or len(est_rows) < 2:
        return None

    eps = [_est_eps(r) for r in est_rows]
    eps = [e for e in eps if e is not None]
    if len(eps) < 2:
        return None

    # QoQ deltas across consecutive rows (newest → oldest): count ups vs downs.
    deltas = [eps[i] - eps[i + 1] for i in range(len(eps) - 1)]
    tol = 1e-6
    ups = sum(1 for d in deltas if d > tol)
    downs = sum(1 for d in deltas if d < -tol)
    revisions_30d = ups - downs

    # est_drift_pct: latest row vs the row ~90d back (index 1 when available;
    # deepest available otherwise — rows are ~91d apart).
    older_idx = 1 if len(eps) > 1 else len(eps) - 1
    older = eps[older_idx]
    est_drift_pct = (eps[0] - older) / abs(older) if older else None

    # Composite breadth: net revision direction dominates; drift adds conviction.
    # Range target ~0-1 around 0.5 neutral.
    breadth = 0.5 + 0.15 * max(-2, min(2, revisions_30d))
    if est_drift_pct is not None:
        # ±5% drift ≈ ±0.20 — a drifted-out estimate is a strong tell.
        breadth += max(-0.20, min(0.20, est_drift_pct * 4.0))
    breadth = max(0.0, min(1.0, breadth))

    if revisions_30d > 0 and (est_drift_pct or 0) > 0.01:
        direction = "rising"
    elif revisions_30d < 0 or (est_drift_pct or 0) < -0.01:
        direction = "falling"
    elif ups and downs:
        direction = "mixed"
    else:
        direction = "flat"

    return {
        "revisions_30d": revisions_30d,
        "est_drift_pct": round(est_drift_pct, 4) if est_drift_pct is not None else None,
        "breadth_score": round(breadth, 3),
        "direction": direction,
        "n_rows": len(eps),
    }


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

    rev = analyst_revision_breadth(config, ticker)
    if rev:
        drift = rev.get("est_drift_pct")
        if drift is not None:
            if drift < -0.05:
                flags.append(f"EPS consensus drifting down {drift:.1%} vs ~90d-ago row")
                score -= 15.0
            elif drift > 0.05:
                score += 10.0

    score = max(0.0, min(100.0, score))
    grade = "A" if score >= 85 else "B" if score >= 70 else "C" if score >= 55 else "D"
    out: dict[str, Any] = {
        "quality_score": round(score, 1),
        "flags": flags,
        "grade": grade,
    }
    if rev:
        out["revision_breadth"] = rev
    return out
