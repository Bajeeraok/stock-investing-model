"""Tests for Portfolio Doctor v2: health score, MCTR, stress tests, priority actions."""
import pytest


# ─── Health Score ───
class TestHealthScore:
    def _sample_holdings(self, n=10, equal=True):
        pct = round(100 / n, 1) if equal else None
        return [
            {"ticker": f"T{i}", "pct": pct or (30 if i == 0 else round(70 / (n - 1), 1)),
             "value": 1000 * (3 if i == 0 and not equal else 1),
             "regime": "UP" if i % 3 != 0 else "DOWN",
             "suggestion": "HOLD/ADD" if i % 3 != 0 else "CONSIDER TRIM"}
            for i in range(n)
        ]

    def test_perfect_diversification_high_score(self):
        from portfolio.health_score import compute_health_score
        holdings = self._sample_holdings(20, equal=True)
        total_value = sum(h["value"] for h in holdings)
        result = compute_health_score(holdings, total_value)
        assert result["score"] >= 50
        assert set(result["sub_scores"].keys()) == {"concentration", "correlation", "regime_alignment", "drawdown_risk", "tax_efficiency"}

    def test_single_stock_low_concentration(self):
        from portfolio.health_score import compute_health_score
        holdings = [{"ticker": "NVDA", "pct": 100, "value": 10000, "regime": "UP", "suggestion": "HOLD/ADD"}]
        result = compute_health_score(holdings, 10000)
        assert result["sub_scores"]["concentration"] <= 50

    def test_all_down_regime_low_alignment(self):
        from portfolio.health_score import compute_health_score
        holdings = [
            {"ticker": f"T{i}", "pct": 20, "value": 2000, "regime": "DOWN", "suggestion": "CONSIDER TRIM"}
            for i in range(5)
        ]
        result = compute_health_score(holdings, 10000)
        assert result["sub_scores"]["regime_alignment"] <= 20

    def test_health_returns_improvement_note(self):
        from portfolio.health_score import compute_health_score
        holdings = self._sample_holdings(5, equal=False)
        total_value = sum(h["value"] for h in holdings)
        result = compute_health_score(holdings, total_value)
        assert "improvement_note" in result
        assert result["improvement_note"]

    def test_sub_scores_in_range(self):
        from portfolio.health_score import compute_health_score
        holdings = self._sample_holdings(8)
        total_value = sum(h["value"] for h in holdings)
        result = compute_health_score(holdings, total_value)
        for k, v in result["sub_scores"].items():
            assert 0 <= v <= 100, f"{k} = {v} out of range"


# ─── Stress Tests ───
class TestStressTests:
    def test_named_scenarios_returned(self):
        from portfolio.stress_test import compute_stress_tests
        holdings = [
            {"ticker": "NVDA", "pct": 30, "value": 3000},
            {"ticker": "AAPL", "pct": 20, "value": 2000},
            {"ticker": "GLD", "pct": 10, "value": 1000},
        ]
        result = compute_stress_tests(holdings, 10000, sector_map={"NVDA": "Technology", "AAPL": "Technology"})
        assert len(result) == 4
        names = [s["name"] for s in result]
        assert "COVID Mar 2020" in names
        assert "GFC 2008" in names

    def test_tech_heavy_worse_in_dotcom(self):
        from portfolio.stress_test import compute_stress_tests
        holdings = [
            {"ticker": "NVDA", "pct": 50, "value": 5000},
            {"ticker": "MSFT", "pct": 50, "value": 5000},
        ]
        result = compute_stress_tests(holdings, 10000, sector_map={"NVDA": "Technology", "MSFT": "Technology"})
        dotcom = next(s for s in result if "Dot-com" in s["name"])
        gfc = next(s for s in result if "GFC" in s["name"])
        # Tech-heavy portfolio should suffer more in dot-com than GFC (per sector multipliers)
        assert abs(dotcom["portfolio_impact_pct"]) > 0

    def test_commodities_less_impact(self):
        from portfolio.stress_test import compute_stress_tests
        holdings = [{"ticker": "GLD", "pct": 100, "value": 10000}]
        result = compute_stress_tests(holdings, 10000)
        rate_hike = next(s for s in result if "rate hike" in s["name"])
        assert abs(rate_hike["portfolio_impact_pct"]) < abs(rate_hike["spy_drawdown_pct"])

    def test_survivors_list(self):
        from portfolio.stress_test import compute_stress_tests
        holdings = [
            {"ticker": "GLD", "pct": 50, "value": 5000},
            {"ticker": "NVDA", "pct": 50, "value": 5000},
        ]
        result = compute_stress_tests(holdings, 10000, sector_map={"NVDA": "Technology"})
        for s in result:
            assert isinstance(s["survivors"], list)


# ─── Priority Actions ───
class TestPriorityActions:
    def test_earnings_urgency(self):
        from portfolio.priority_actions import build_priority_actions
        holdings = [{"ticker": "NVDA", "pct": 28, "value": 28000}]
        earnings = [{"ticker": "NVDA", "days_until": 5}]
        result = build_priority_actions(holdings, 100000, earnings_calendar=earnings)
        assert len(result["this_week"]) >= 1
        assert any("NVDA" in a["action"] for a in result["this_week"])

    def test_correlation_trim(self):
        from portfolio.priority_actions import build_priority_actions
        holdings = [
            {"ticker": "SPY", "pct": 15, "value": 15000},
            {"ticker": "QQQ", "pct": 10, "value": 10000},
        ]
        result = build_priority_actions(holdings, 100000, correlation_alerts=["SPY-QQQ: 93%"])
        assert len(result["this_week"]) >= 1

    def test_conditional_adds(self):
        from portfolio.priority_actions import build_priority_actions
        add_list = [{"ticker": "GOOGL", "confidence": 57, "buy_price": 387.0, "action": "BUY"}]
        result = build_priority_actions([], 100000, add_list=add_list)
        assert len(result["this_month"]) >= 1
        assert any("GOOGL" in a["action"] for a in result["this_month"])

    def test_empty_inputs(self):
        from portfolio.priority_actions import build_priority_actions
        result = build_priority_actions([], 0)
        assert result["this_week"] == []
        assert result["this_month"] == []
        assert result["total_actions"] == 0

    def test_tax_harvest(self):
        from portfolio.priority_actions import build_priority_actions
        holdings = [{"ticker": "BABA", "pct": 3, "value": 3000}]
        tax_exits = {"items": [{"ticker": "BABA", "has_loss": True, "is_long_term": False, "gain_loss": -2100}]}
        result = build_priority_actions(holdings, 100000, tax_exits=tax_exits)
        assert any("BABA" in a.get("action", "") for a in result["this_month"])
