"""FMP fundamental gate + entry conviction (uses project FMP API key from config)."""
from __future__ import annotations

import logging
from typing import Any, Optional

import requests

from ..fmp_client import BASE_V3, get_api_key

from .models import EntryConviction, FundamentalMetrics

logger = logging.getLogger(__name__)


class FMPFundamentalGate:
    """Pull key fundamentals from FMP v3 and run gate + conviction."""

    def __init__(self, config: dict | None = None):
        self._config = config or {}
        self._api_key = get_api_key(self._config) or ""

    def _get(self, endpoint: str, params: dict | None = None) -> Any:
        params = dict(params or {})
        if not self._api_key:
            logger.warning("FMP API key missing — fundamental gate will return empty")
            return {}
        params["apikey"] = self._api_key
        url = f"{BASE_V3}/{endpoint.lstrip('/')}"
        try:
            r = requests.get(url, params=params, timeout=15)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            logger.warning("FMP API error [%s]: %s", endpoint, e)
            return {}

    def fetch_metrics(self, ticker: str) -> FundamentalMetrics:
        m = FundamentalMetrics(ticker=ticker)

        income = self._get(f"income-statement/{ticker}", {"limit": 3, "period": "annual"})
        if income and len(income) >= 2:
            curr, prev = income[0], income[1]
            curr_rev = curr.get("revenue", 0)
            prev_rev = prev.get("revenue", 1)
            m.revenue_growth_yoy = (curr_rev - prev_rev) / abs(prev_rev) if prev_rev else None
            m.revenue_ttm = curr_rev
            curr_gm = curr.get("grossProfitRatio", None)
            prev_gm = prev.get("grossProfitRatio", None)
            m.gross_margin = curr_gm
            m.gross_margin_change = (curr_gm - prev_gm) if (curr_gm is not None and prev_gm is not None) else None
            m.net_income_ttm = curr.get("netIncome", None)

        cf = self._get(f"cash-flow-statement/{ticker}", {"limit": 2, "period": "annual"})
        if cf and len(cf) >= 1:
            m.fcf = cf[0].get("freeCashFlow", None)

        km = self._get(f"key-metrics/{ticker}", {"limit": 2, "period": "annual"})
        if km and len(km) >= 1:
            m.fcf_yield = km[0].get("freeCashFlowYield", None)
            m.pe_ratio = km[0].get("peRatio", None)
            curr_dte = km[0].get("debtToEquity", None)
            prev_dte = km[1].get("debtToEquity", None) if len(km) > 1 else None
            m.debt_to_equity = curr_dte
            m.debt_to_equity_change = (curr_dte - prev_dte) if (curr_dte is not None and prev_dte is not None) else None

        earnings = self._get(f"earnings-surprises/{ticker}")
        if earnings and len(earnings) >= 4:
            recent = earnings[:8]
            beats = sum(
                1
                for e in recent
                if e.get("actualEarningResult", 0) >= e.get("estimatedEarning", 0)
            )
            m.eps_beat_rate = beats / len(recent)

        pt = self._get(f"price-target-consensus/{ticker}")
        if pt and isinstance(pt, list) and len(pt) > 0:
            m.analyst_target = pt[0].get("targetConsensus", None)
        elif pt and isinstance(pt, dict):
            m.analyst_target = pt.get("targetConsensus", None)

        return m

    def validate_fair_value(
        self,
        ticker: str,
        calculated_fv: float,
        current_price: float,
        analyst_target: Optional[float],
    ) -> dict:
        issues: list[str] = []
        discount = 0.0
        if calculated_fv > 0:
            discount = (calculated_fv - current_price) / calculated_fv

        if calculated_fv > current_price * 3.0:
            issues.append(
                f"FV ${calculated_fv:.2f} > 3x current — check fair_value_estimator / inputs"
            )

        if discount > 0.60:
            issues.append(f"Discount {discount:.0%} > 60% — validate FV inputs")

        if analyst_target:
            divergence = abs(calculated_fv - analyst_target) / analyst_target
            if divergence > 0.40:
                issues.append(
                    f"Your FV ${calculated_fv:.2f} diverges {divergence:.0%} from analyst target ${analyst_target:.2f}"
                )

        return {
            "valid": len(issues) == 0,
            "discount": round(discount, 4),
            "issues": issues,
            "analyst_target": analyst_target,
        }

    def run_fundamental_gate(self, metrics: FundamentalMetrics) -> dict:
        results: dict[str, str] = {}
        score = 100
        warnings: list[str] = []
        failures: list[str] = []

        rg = metrics.revenue_growth_yoy
        if rg is not None:
            if rg < 0:
                results["revenue_growth"] = "FAIL"
                failures.append(f"Revenue declining {rg:.1%} YoY")
                score -= 25
            elif rg < 0.05:
                results["revenue_growth"] = "WARN"
                warnings.append(f"Revenue growth slow {rg:.1%} YoY")
                score -= 10
            else:
                results["revenue_growth"] = "PASS"
        else:
            results["revenue_growth"] = "UNKNOWN"
            score -= 5

        gmc = metrics.gross_margin_change
        if gmc is not None:
            if gmc < -0.05:
                results["gross_margin"] = "FAIL"
                failures.append(f"Gross margin compressed {gmc:.1%}")
                score -= 20
            elif gmc < -0.02:
                results["gross_margin"] = "WARN"
                warnings.append(f"Gross margin slight compression {gmc:.1%}")
                score -= 8
            else:
                results["gross_margin"] = "PASS"
        else:
            results["gross_margin"] = "UNKNOWN"
            score -= 3

        fcf = metrics.fcf_yield
        if fcf is not None:
            if fcf < 0:
                results["fcf"] = "FAIL"
                failures.append(f"Negative FCF yield {fcf:.1%}")
                score -= 25
            elif fcf < 0.02:
                results["fcf"] = "WARN"
                warnings.append(f"Low FCF yield {fcf:.1%}")
                score -= 8
            else:
                results["fcf"] = "PASS"
        else:
            results["fcf"] = "UNKNOWN"
            score -= 5

        eps = metrics.eps_beat_rate
        if eps is not None:
            if eps < 0.40:
                results["eps_beat_rate"] = "FAIL"
                failures.append(f"Missing majority of EPS estimates {eps:.0%}")
                score -= 20
            elif eps < 0.60:
                results["eps_beat_rate"] = "WARN"
                warnings.append(f"EPS beat rate below average {eps:.0%}")
                score -= 8
            else:
                results["eps_beat_rate"] = "PASS"
        else:
            results["eps_beat_rate"] = "UNKNOWN"
            score -= 3

        dtec = metrics.debt_to_equity_change
        if dtec is not None:
            if dtec > 0.50:
                results["debt"] = "FAIL"
                failures.append(f"Rapid leverage increase {dtec:.1%}")
                score -= 15
            elif dtec > 0.20:
                results["debt"] = "WARN"
                warnings.append(f"Debt increasing {dtec:.1%}")
                score -= 5
            else:
                results["debt"] = "PASS"
        else:
            results["debt"] = "UNKNOWN"

        score = max(0, min(100, score))

        if len(failures) >= 2 or score < 40:
            gate = "FAIL"
            action = "AVOID"
        elif len(failures) == 1 or score < 65:
            gate = "WARN"
            action = "WATCH"
        else:
            gate = "PASS"
            action = "PROCEED"

        return {
            "gate": gate,
            "action": action,
            "score": score,
            "failures": failures,
            "warnings": warnings,
            "per_metric": results,
        }

    def compute_entry_conviction(
        self,
        ticker: str,
        current_price: float,
        fair_value: float,
        gate_result: dict,
        fv_validation: dict,
        profile: str = "long_term",
    ) -> EntryConviction:
        fund_score = gate_result["score"]
        action = gate_result["action"]
        discount = float(fv_validation.get("discount") or 0.0)

        if action == "AVOID":
            return EntryConviction(
                ticker=ticker,
                profile=profile,
                action="AVOID",
                conviction="NONE",
                suggested_size=0.0,
                entry_zone_low=0,
                entry_zone_high=0,
                stop=0,
                target_1=0,
                target_2=0,
                fundamental_score=fund_score,
                trim_triggers=gate_result["failures"],
                warnings=gate_result["warnings"],
                rationale="Fundamental gate failed — do not enter",
            )

        if not fv_validation["valid"]:
            return EntryConviction(
                ticker=ticker,
                profile=profile,
                action="WAIT",
                conviction="LOW",
                suggested_size=0.0,
                entry_zone_low=0,
                entry_zone_high=0,
                stop=0,
                target_1=0,
                target_2=0,
                fundamental_score=fund_score,
                trim_triggers=[],
                warnings=fv_validation["issues"],
                rationale="Fair value validation failed — fix estimator first",
            )

        if discount >= 0.30 and fund_score >= 75:
            conviction = "HIGH"
            initial_size = 0.40
            entry_low = current_price * 0.97
            entry_high = current_price * 1.02
            rationale = (
                f"{discount:.0%} below fair value + strong fundamentals "
                f"(score {fund_score}/100) — high conviction entry"
            )
        elif discount >= 0.20 and fund_score >= 65:
            conviction = "MEDIUM"
            initial_size = 0.25
            entry_low = current_price * 0.96
            entry_high = current_price * 1.01
            rationale = (
                f"{discount:.0%} below fair value + solid fundamentals "
                f"(score {fund_score}/100) — medium conviction entry"
            )
        elif discount >= 0.10 and fund_score >= 60:
            conviction = "LOW"
            initial_size = 0.10
            entry_low = fair_value * 0.78
            entry_high = fair_value * 0.82
            rationale = (
                f"Modest discount {discount:.0%} — wait for price to reach "
                f"${entry_low:.2f}–${entry_high:.2f} before entering"
            )
        else:
            conviction = "NONE"
            initial_size = 0.0
            entry_low = fair_value * 0.72
            entry_high = fair_value * 0.78
            rationale = (
                f"Insufficient discount {discount:.0%} or weak fundamentals — wait for better entry"
            )

        stop = round(current_price * 0.88, 2)
        target_1 = round(fair_value * 0.95, 2)
        target_2 = round(fair_value * 1.10, 2)

        return EntryConviction(
            ticker=ticker,
            profile=profile,
            action="ENTER" if initial_size > 0 else "WAIT",
            conviction=conviction,
            suggested_size=initial_size,
            entry_zone_low=round(entry_low, 2),
            entry_zone_high=round(entry_high, 2),
            stop=stop,
            target_1=target_1,
            target_2=target_2,
            fundamental_score=fund_score,
            trim_triggers=gate_result["failures"],
            warnings=gate_result["warnings"],
            rationale=rationale,
        )
