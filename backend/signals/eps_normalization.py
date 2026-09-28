"""
eps_normalization.py — detect and strip large one-time/non-operating swings out of
TTM EPS before it feeds the fair-value model.

Root cause this guards against: `trailing_eps` (and therefore `ttm_pe`) comes straight
from FMP's raw GAAP net-income-per-share (signals/fetcher.py's `trailingEps`). GAAP net
income includes non-operating items — most visibly, large mark-to-market gains/losses on
equity investments that several mega-caps (Alphabet, among others) now report under ASU
2016-01. A big one-time gain quarter inflates TTM EPS, which makes TTM P/E look
artificially low ("cheap") and inflates the fair-value estimator's output for a stock
that isn't actually any cheaper operationally. Confirmed case: Alphabet's Q2 included a
~$77.1B / ~$6.26-per-share gain on equity securities (Anthropic, SpaceX stakes); backing
that out moves TTM EPS from ~$19.88 to ~$13.60 (TTM P/E ~17x -> ~25x).

This is a heuristic, not a precise non-GAAP reconciliation: FMP's standard income
statement only exposes a single "other income/expense, net" line, which also carries
legitimate recurring items (interest income/expense) that a full strip would remove too.
To avoid over-correcting ordinary companies (where other income is small and normal), the
adjustment only triggers when a quarter's other-income magnitude is large relative to that
quarter's operating income — the signature of an unusual, non-recurring item rather than
routine interest income. When it doesn't trigger, this is a no-op and the raw GAAP EPS is
used exactly as before.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# A quarter's |other income/expense, net| must exceed BOTH of these to count as an
# anomalous non-operating swing worth excluding — relative (vs that quarter's operating
# income) so it scales with company size, and absolute so a tiny/near-zero operating
# income quarter doesn't trigger on a modest dollar swing.
_ANOMALY_REL_THRESHOLD = 0.40  # other income/expense > 40% of operating income
_ANOMALY_ABS_THRESHOLD_USD = 500_000_000  # and > $500M


def _safe_float(v: Any) -> float | None:
    try:
        f = float(v)
        return f if f == f else None  # filter NaN
    except (TypeError, ValueError):
        return None


@dataclass
class CoreEpsResult:
    gaap_ttm_eps: float | None
    core_ttm_eps: float | None
    adjusted: bool
    quarters_used: int
    anomalous_quarters: list[str] = field(default_factory=list)  # e.g. ["2026-Q2"]
    notes: list[str] = field(default_factory=list)
    error: str | None = None


def compute_core_ttm_eps(
    quarterly_rows: list[dict[str, Any]] | None,
) -> CoreEpsResult:
    """
    quarterly_rows: FMP /income-statement rows, newest first (as returned by
    signals.fv_eps_history.fetch_quarterly_income) — at least 4 needed to compute a TTM
    figure; fewer/None degrades to "no adjustment possible" rather than erroring.
    """
    if not quarterly_rows or len(quarterly_rows) < 4:
        return CoreEpsResult(
            gaap_ttm_eps=None, core_ttm_eps=None, adjusted=False, quarters_used=0,
            notes=["Fewer than 4 quarterly income statements available — cannot compute TTM EPS adjustment."],
        )

    ttm = quarterly_rows[:4]
    shares = _safe_float(ttm[0].get("weightedAverageShsOutDil") or ttm[0].get("weightedAverageShsOut"))
    if not shares or shares <= 0:
        return CoreEpsResult(
            gaap_ttm_eps=None, core_ttm_eps=None, adjusted=False, quarters_used=len(ttm),
            notes=["No diluted share count available — cannot compute TTM EPS adjustment."],
        )

    ttm_net_income = 0.0
    core_net_income = 0.0
    anomalous_quarters: list[str] = []
    for q in ttm:
        net_income = _safe_float(q.get("netIncome"))
        operating_income = _safe_float(q.get("operatingIncome"))
        other_net = _safe_float(q.get("totalOtherIncomeExpensesNet"))
        income_before_tax = _safe_float(q.get("incomeBeforeTax"))
        tax_expense = _safe_float(q.get("incomeTaxExpense"))
        if net_income is None:
            return CoreEpsResult(
                gaap_ttm_eps=None, core_ttm_eps=None, adjusted=False, quarters_used=len(ttm),
                notes=["A quarterly row is missing netIncome — cannot compute TTM EPS adjustment."],
            )
        ttm_net_income += net_income
        contribution = net_income
        if (
            other_net is not None
            and operating_income is not None
            and operating_income != 0
            and abs(other_net) > _ANOMALY_ABS_THRESHOLD_USD
            and abs(other_net) > _ANOMALY_REL_THRESHOLD * abs(operating_income)
        ):
            # Remove this quarter's other-income/expense at its own effective tax rate —
            # a plain pre-tax strip would overstate the adjustment for a taxed gain.
            eff_tax_rate = 0.21  # US statutory corporate rate — used as a fallback
            if income_before_tax and tax_expense is not None and income_before_tax != 0:
                implied = tax_expense / income_before_tax
                if 0.0 <= implied <= 0.6:
                    eff_tax_rate = implied
            contribution = net_income - other_net * (1 - eff_tax_rate)
            period = q.get("date") or q.get("period") or q.get("calendarYear") or "unknown quarter"
            anomalous_quarters.append(str(period))
        core_net_income += contribution

    gaap_eps = round(ttm_net_income / shares, 4)
    core_eps = round(core_net_income / shares, 4)
    adjusted = bool(anomalous_quarters) and abs(core_eps - gaap_eps) > 0.01

    notes: list[str] = []
    if adjusted:
        notes.append(
            f"TTM EPS adjusted for an unusually large non-operating item in "
            f"{', '.join(anomalous_quarters)} (other income/expense far exceeding that "
            f"quarter's operating income — the signature of a one-time gain/loss, e.g. "
            f"mark-to-market on equity investments, not recurring interest income/expense). "
            f"GAAP TTM EPS ${gaap_eps:.2f} -> core TTM EPS ${core_eps:.2f}. This also removes "
            f"any smaller, legitimate recurring items in the same 'other income' line for "
            f"that quarter — a heuristic, not a precise non-GAAP reconciliation."
        )

    return CoreEpsResult(
        gaap_ttm_eps=gaap_eps,
        core_ttm_eps=core_eps,
        adjusted=adjusted,
        quarters_used=len(ttm),
        anomalous_quarters=anomalous_quarters,
        notes=notes,
    )
