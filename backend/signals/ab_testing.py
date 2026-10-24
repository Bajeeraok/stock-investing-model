"""
A/B testing framework for gradual model rollout.

Implements safe, controlled rollout of model improvements with:
- User cohort assignment
- Statistical comparison between control and treatment
- Automatic rollback if treatment underperforms
- Gradual traffic increase (1% → 5% → 10% → 50% → 100%)

This follows engineering best practices for production ML deployment.
"""
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class ABTestConfig:
    """Configuration for A/B test."""
    
    def __init__(
        self,
        test_name: str,
        treatment_enabled: bool = False,
        traffic_percentage: float = 0.0,  # 0.0 to 1.0
        user_cohorts: dict[str, float] | None = None,
        min_sample_size: int = 100,
        significance_threshold: float = 0.05,
        rollback_on_degradation: bool = True,
        max_degradation_pct: float = 5.0,
    ):
        self.test_name = test_name
        self.treatment_enabled = treatment_enabled
        self.traffic_percentage = traffic_percentage
        self.user_cohorts = user_cohorts or {}
        self.min_sample_size = min_sample_size
        self.significance_threshold = significance_threshold
        self.rollback_on_degradation = rollback_on_degradation
        self.max_degradation_pct = max_degradation_pct


def assign_cohort(
    user_id: str | None,
    test_config: ABTestConfig,
) -> str:
    """
    Assign user to control or treatment cohort.
    
    Uses consistent hashing to ensure same user always gets same cohort.
    """
    if not user_id:
        # No user ID - default to control
        return "control"
    
    if not test_config.treatment_enabled:
        return "control"
    
    # Hash user ID to get consistent assignment
    hash_val = int(hashlib.md5(user_id.encode()).hexdigest(), 16)
    hash_pct = (hash_val % 10000) / 10000.0  # 0.0 to 1.0
    
    # Check specific cohort assignments
    for cohort, threshold in test_config.user_cohorts.items():
        if hash_pct < threshold:
            return cohort
    
    # Use traffic percentage
    if hash_pct < test_config.traffic_percentage:
        return "treatment"
    
    return "control"


def assign_ensemble_method(
    user_id: str | None,
    test_config: ABTestConfig,
) -> str:
    """
    Assign ensemble method based on A/B test.
    
    Returns the ensemble method to use for this user.
    """
    cohort = assign_cohort(user_id, test_config)
    
    if cohort == "treatment":
        # Treatment gets new ensemble method
        return "dynamic"  # or whichever method you're testing
    else:
        # Control gets baseline
        return "weighted_average"


class ABTestMetrics:
    """Track metrics for control and treatment cohorts."""
    
    def __init__(self, test_name: str):
        self.test_name = test_name
        self.control_metrics: list[dict] = []
        self.treatment_metrics: list[dict] = []
    
    def record_metric(
        self,
        cohort: str,
        hit: bool,
        return_pct: float,
        timestamp: str,
    ) -> None:
        """Record a single metric observation."""
        metric = {
            "hit": hit,
            "return_pct": return_pct,
            "timestamp": timestamp,
        }
        
        if cohort == "control":
            self.control_metrics.append(metric)
        elif cohort == "treatment":
            self.treatment_metrics.append(metric)
    
    def get_summary(self) -> dict[str, Any]:
        """Calculate summary statistics for both cohorts."""
        summary = {
            "test_name": self.test_name,
            "control": {},
            "treatment": {},
            "comparison": {},
        }
        
        # Control summary
        if self.control_metrics:
            control_hits = sum(1 for m in self.control_metrics if m["hit"])
            control_returns = [m["return_pct"] for m in self.control_metrics]
            
            summary["control"] = {
                "n": len(self.control_metrics),
                "hit_rate": control_hits / len(self.control_metrics),
                "mean_return": sum(control_returns) / len(control_returns),
                "std_return": (sum((r - sum(control_returns)/len(control_returns))**2 for r in control_returns) / len(control_returns))**0.5,
            }
        
        # Treatment summary
        if self.treatment_metrics:
            treatment_hits = sum(1 for m in self.treatment_metrics if m["hit"])
            treatment_returns = [m["return_pct"] for m in self.treatment_metrics]
            
            summary["treatment"] = {
                "n": len(self.treatment_metrics),
                "hit_rate": treatment_hits / len(self.treatment_metrics),
                "mean_return": sum(treatment_returns) / len(treatment_returns),
                "std_return": (sum((r - sum(treatment_returns)/len(treatment_returns))**2 for r in treatment_returns) / len(treatment_returns))**0.5,
            }
        
        # Comparison
        if self.control_metrics and self.treatment_metrics:
            control_mean = summary["control"]["mean_return"]
            treatment_mean = summary["treatment"]["mean_return"]
            
            summary["comparison"] = {
                "hit_rate_lift": summary["treatment"]["hit_rate"] - summary["control"]["hit_rate"],
                "return_lift": treatment_mean - control_mean,
                "relative_lift": (treatment_mean - control_mean) / abs(control_mean) if control_mean != 0 else 0,
            }
        
        return summary
    
    def should_rollback(self, test_config: ABTestConfig) -> tuple[bool, str]:
        """
        Determine if test should rollback based on metrics.
        
        Returns (should_rollback, reason).
        """
        summary = self.get_summary()
        
        # Not enough data
        if summary["control"].get("n", 0) < test_config.min_sample_size:
            return False, "insufficient_data"
        
        if summary["treatment"].get("n", 0) < test_config.min_sample_size:
            return False, "insufficient_data"
        
        # Check for degradation
        return_lift = summary["comparison"].get("return_lift", 0)
        
        if return_lift < -test_config.max_degradation_pct:
            if test_config.rollback_on_degradation:
                return True, f"treatment underperforms by {abs(return_lift):.2f}%"
        
        return False, "ok"


def load_ab_test_config(config_path: str | Path | None = None) -> ABTestConfig:
    """Load A/B test configuration from file."""
    if config_path is None:
        config_path = Path("data/ab_test_config.json")
    
    if not isinstance(config_path, Path):
        config_path = Path(config_path)
    
    if not config_path.exists():
        # Return default config
        return ABTestConfig(
            test_name="ensemble_method_test",
            treatment_enabled=False,
            traffic_percentage=0.0,
        )
    
    try:
        with open(config_path, encoding="utf-8") as f:
            data = json.load(f)
        
        return ABTestConfig(
            test_name=data.get("test_name", "ensemble_method_test"),
            treatment_enabled=data.get("treatment_enabled", False),
            traffic_percentage=data.get("traffic_percentage", 0.0),
            user_cohorts=data.get("user_cohorts"),
            min_sample_size=data.get("min_sample_size", 100),
            significance_threshold=data.get("significance_threshold", 0.05),
            rollback_on_degradation=data.get("rollback_on_degradation", True),
            max_degradation_pct=data.get("max_degradation_pct", 5.0),
        )
    except Exception as e:
        logger.warning(f"Failed to load A/B test config: {e}, using defaults")
        return ABTestConfig(
            test_name="ensemble_method_test",
            treatment_enabled=False,
            traffic_percentage=0.0,
        )


def save_ab_test_config(config: ABTestConfig, config_path: str | Path | None = None) -> None:
    """Save A/B test configuration to file."""
    if config_path is None:
        config_path = Path("data/ab_test_config.json")
    
    if not isinstance(config_path, Path):
        config_path = Path(config_path)
    
    config_path.parent.mkdir(parents=True, exist_ok=True)
    
    data = {
        "test_name": config.test_name,
        "treatment_enabled": config.treatment_enabled,
        "traffic_percentage": config.traffic_percentage,
        "user_cohorts": config.user_cohorts,
        "min_sample_size": config.min_sample_size,
        "significance_threshold": config.significance_threshold,
        "rollback_on_degradation": config.rollback_on_degradation,
        "max_degradation_pct": config.max_degradation_pct,
    }
    
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def gradual_rollout_schedule(traffic_percentage: float) -> float:
    """
    Calculate next traffic percentage for gradual rollout.
    
    Schedule: 1% → 5% → 10% → 25% → 50% → 100%
    """
    if traffic_percentage < 0.01:
        return 0.01  # 1%
    elif traffic_percentage < 0.05:
        return 0.05  # 5%
    elif traffic_percentage < 0.10:
        return 0.10  # 10%
    elif traffic_percentage < 0.25:
        return 0.25  # 25%
    elif traffic_percentage < 0.50:
        return 0.50  # 50%
    else:
        return 1.00  # 100%


def should_increase_traffic(
    metrics: ABTestMetrics,
    config: ABTestConfig,
) -> tuple[bool, str]:
    """
    Determine if traffic should be increased to treatment.
    
    Returns (should_increase, reason).
    """
    summary = metrics.get_summary()
    
    # Not enough data
    if summary["control"].get("n", 0) < config.min_sample_size:
        return False, "insufficient_control_data"
    
    if summary["treatment"].get("n", 0) < config.min_sample_size:
        return False, "insufficient_treatment_data"
    
    # Check if treatment is performing well
    return_lift = summary["comparison"].get("return_lift", 0)
    hit_rate_lift = summary["comparison"].get("hit_rate_lift", 0)
    
    # Treatment must have positive lift in both metrics
    if return_lift > 0 and hit_rate_lift > 0:
        return True, "treatment_outperforms"
    
    return False, "treatment_not_outperforming"


def apply_ab_test_to_signal(
    signal_data: dict[str, Any],
    user_id: str | None,
    config: ABTestConfig | None = None,
) -> dict[str, Any]:
    """
    Apply A/B test to signal generation.
    
    Selects ensemble method based on user cohort assignment.
    """
    if config is None:
        config = load_ab_test_config()
    
    if not config.treatment_enabled:
        # Test not enabled - use baseline
        method = "weighted_average"
    else:
        method = assign_ensemble_method(user_id, config)
    
    # Apply ensemble method
    from signals.ensemble_methods import apply_ensemble_to_signal
    
    signal_data = apply_ensemble_to_signal(
        signal_data,
        method=method,
        regime_bull_pct=signal_data.get("regime_bull_pct"),
        volatility_factor=signal_data.get("volatility_factor", 1.0),
    )
    
    # Add A/B test metadata
    signal_data["ab_test"] = {
        "test_name": config.test_name,
        "cohort": assign_cohort(user_id, config),
        "ensemble_method": method,
        "traffic_percentage": config.traffic_percentage,
    }
    
    return signal_data
