"""
Statistical significance testing for signal quality validation.

Implements proper statistical tests to validate that signal improvements
are statistically significant and not due to random chance.

Tests implemented:
1. Binomial test for hit rate significance
2. Bootstrap confidence intervals for mean returns
3. Paired t-test for comparing before/after performance
4. Information Ratio calculation
5. Sharpe Ratio calculation

This follows quantitative finance best practices for model validation.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


def binomial_test_hit_rate(
    hits: int,
    total: int,
    null_hypothesis: float = 0.5,
) -> dict[str, Any]:
    """
    Test if hit rate is significantly different from null hypothesis.
    
    Uses binomial test to determine if observed hit rate is statistically
    significantly different from the null (e.g., 50% for random).
    
    Args:
        hits: Number of positive outcomes
        total: Total number of observations
        null_hypothesis: Expected hit rate under null (default 0.5 for random)
    
    Returns:
        Dictionary with p_value, is_significant, hit_rate, etc.
    """
    if total == 0:
        return {"error": "total cannot be zero"}
    
    hit_rate = hits / total
    
    try:
        from scipy import stats
        
        # Binomial test (scipy.stats.binomtest in newer versions, binom_test in older)
        if hasattr(stats, 'binomtest'):
            result = stats.binomtest(hits, total, null_hypothesis, alternative='greater')
            p_value = result.pvalue
        else:
            # Fallback to binom_test for older scipy versions
            result = stats.binom_test(hits, total, null_hypothesis, alternative='greater')
            p_value = result.pvalue
        
        # Significance at 5% level
        is_significant = p_value < 0.05
        
        # Effect size (Cohen's h)
        h = 2 * np.arcsin(np.sqrt(hit_rate)) - 2 * np.arcsin(np.sqrt(null_hypothesis))
        
        return {
            "hits": hits,
            "total": total,
            "hit_rate": round(hit_rate, 4),
            "null_hypothesis": null_hypothesis,
            "p_value": round(float(p_value), 6),
            "is_significant": bool(is_significant),
            "effect_size_h": round(float(h), 4),
            "interpretation": "Significant" if is_significant else "Not significant",
        }
    except ImportError:
        logger.warning("scipy not available, using normal approximation")
        # Normal approximation
        se = np.sqrt(null_hypothesis * (1 - null_hypothesis) / total)
        z = (hit_rate - null_hypothesis) / se
        p_value = 1 - stats.norm.cdf(z) if 'stats' in locals() else 0.5
        
        return {
            "hits": hits,
            "total": total,
            "hit_rate": round(hit_rate, 4),
            "null_hypothesis": null_hypothesis,
            "p_value": round(float(p_value), 6),
            "is_significant": bool(p_value < 0.05),
            "method": "normal_approximation",
        }


def bootstrap_confidence_interval(
    returns: list[float],
    n_bootstrap: int = 10000,
    confidence_level: float = 0.95,
) -> dict[str, Any]:
    """
    Calculate bootstrap confidence interval for mean returns.
    
    Uses resampling to estimate uncertainty in mean return estimate.
    More robust than parametric methods for non-normal distributions.
    
    Args:
        returns: List of percentage returns
        n_bootstrap: Number of bootstrap samples
        confidence_level: Confidence level (e.g., 0.95 for 95% CI)
    
    Returns:
        Dictionary with mean, ci_lower, ci_upper, std_error
    """
    if not returns:
        return {"error": "no returns provided"}
    
    returns_array = np.array(returns)
    n = len(returns_array)
    
    # Bootstrap resampling
    bootstrap_means = []
    for _ in range(n_bootstrap):
        sample = np.random.choice(returns_array, size=n, replace=True)
        bootstrap_means.append(np.mean(sample))
    
    bootstrap_means = np.array(bootstrap_means)
    
    # Calculate percentiles
    alpha = 1 - confidence_level
    ci_lower = np.percentile(bootstrap_means, 100 * alpha / 2)
    ci_upper = np.percentile(bootstrap_means, 100 * (1 - alpha / 2))
    
    # Standard error of the mean
    std_error = np.std(bootstrap_means, ddof=1)
    
    return {
        "mean": round(float(np.mean(returns_array)), 4),
        "std": round(float(np.std(returns_array, ddof=1)), 4),
        "std_error": round(float(std_error), 4),
        "ci_lower": round(float(ci_lower), 4),
        "ci_upper": round(float(ci_upper), 4),
        "confidence_level": confidence_level,
        "n_bootstrap": n_bootstrap,
        "n_observations": n,
    }


def paired_t_test(
    returns_before: list[float],
    returns_after: list[float],
) -> dict[str, Any]:
    """
    Paired t-test to compare before/after performance.
    
    Tests whether improvement after changes is statistically significant.
    Useful for A/B testing or before/after model changes.
    
    Args:
        returns_before: Returns before the change
        returns_after: Returns after the change
    
    Returns:
        Dictionary with t_statistic, p_value, mean_difference, etc.
    """
    if len(returns_before) != len(returns_after):
        return {"error": "returns lists must have same length"}
    
    if len(returns_before) < 2:
        return {"error": "need at least 2 observations"}
    
    try:
        from scipy import stats
        
        differences = np.array(returns_after) - np.array(returns_before)
        mean_diff = np.mean(differences)
        std_diff = np.std(differences, ddof=1)
        
        t_stat, p_value = stats.ttest_rel(returns_after, returns_before, alternative='greater')
        
        return {
            "n": len(returns_before),
            "mean_before": round(float(np.mean(returns_before)), 4),
            "mean_after": round(float(np.mean(returns_after)), 4),
            "mean_difference": round(float(mean_diff), 4),
            "std_difference": round(float(std_diff), 4),
            "t_statistic": round(float(t_stat), 4),
            "p_value": round(float(p_value), 6),
            "is_significant": bool(p_value < 0.05),
            "interpretation": "Significant improvement" if p_value < 0.05 else "Not significant",
        }
    except ImportError:
        logger.warning("scipy not available")
        return {"error": "scipy required for t-test"}


def calculate_sharpe_ratio(
    returns: list[float],
    risk_free_rate: float = 0.02,
    periods_per_year: int = 252,
) -> dict[str, Any]:
    """
    Calculate Sharpe Ratio for signal performance.
    
    Standard risk-adjusted return metric in quantitative finance.
    
    Args:
        returns: List of percentage returns
        risk_free_rate: Annual risk-free rate (default 2%)
        periods_per_year: Trading periods per year (default 252 for daily)
    
    Returns:
        Dictionary with sharpe_ratio, annualized_return, annualized_volatility
    """
    if not returns:
        return {"error": "no returns provided"}
    
    returns_array = np.array(returns)
    
    # Annualized metrics
    annualized_return = np.mean(returns_array) * periods_per_year / 100
    annualized_volatility = np.std(returns_array, ddof=1) * np.sqrt(periods_per_year) / 100
    
    # Sharpe ratio
    excess_return = annualized_return - risk_free_rate
    sharpe = excess_return / annualized_volatility if annualized_volatility > 0 else 0
    
    return {
        "sharpe_ratio": round(sharpe, 4),
        "annualized_return": round(annualized_return, 4),
        "annualized_volatility": round(annualized_volatility, 4),
        "excess_return": round(excess_return, 4),
        "risk_free_rate": risk_free_rate,
        "periods_per_year": periods_per_year,
        "n_observations": len(returns),
    }


def calculate_information_ratio(
    returns: list[float],
    benchmark_returns: list[float],
) -> dict[str, Any]:
    """
    Calculate Information Ratio (active return / tracking error).
    
    Measures risk-adjusted return relative to a benchmark.
    Commonly used to evaluate active fund managers.
    
    Args:
        returns: Strategy returns
        benchmark_returns: Benchmark returns (e.g., SPY)
    
    Returns:
        Dictionary with information_ratio, tracking_error, alpha
    """
    if len(returns) != len(benchmark_returns):
        return {"error": "returns and benchmark must have same length"}
    
    if not returns:
        return {"error": "no returns provided"}
    
    returns_array = np.array(returns)
    benchmark_array = np.array(benchmark_returns)
    
    # Active returns (excess over benchmark)
    active_returns = returns_array - benchmark_array
    
    # Tracking error (std of active returns)
    tracking_error = np.std(active_returns, ddof=1)
    
    # Information Ratio
    information_ratio = np.mean(active_returns) / tracking_error if tracking_error > 0 else 0
    
    # Alpha (average active return)
    alpha = np.mean(active_returns)
    
    return {
        "information_ratio": round(information_ratio, 4),
        "tracking_error": round(tracking_error, 4),
        "alpha": round(alpha, 4),
        "n_observations": len(returns),
    }


def calculate_max_drawdown(
    returns: list[float],
) -> dict[str, Any]:
    """
    Calculate maximum drawdown from returns.
    
    Important risk metric - measures largest peak-to-trough decline.
    
    Args:
        returns: List of percentage returns
    
    Returns:
        Dictionary with max_drawdown, drawdown_duration, etc.
    """
    if not returns:
        return {"error": "no returns provided"}
    
    returns_array = np.array(returns)
    
    # Convert to cumulative returns
    cumulative = np.cumprod(1 + returns_array / 100)
    
    # Running maximum
    running_max = np.maximum.accumulate(cumulative)
    
    # Drawdown from peak
    drawdown = (cumulative - running_max) / running_max
    
    # Maximum drawdown
    max_dd = np.min(drawdown)
    
    # Find drawdown duration
    dd_start = np.argmax(drawdown == max_dd)
    dd_end = len(drawdown) - 1
    dd_duration = dd_end - dd_start
    
    return {
        "max_drawdown": round(max_dd * 100, 2),  # Convert to percentage
        "drawdown_duration": dd_duration,
        "n_observations": len(returns),
    }


def validate_signal_quality(
    buy_returns: list[float],
    hold_returns: list[float] | None = None,
    benchmark_returns: list[float] | None = None,
    risk_free_rate: float = 0.02,
) -> dict[str, Any]:
    """
    Comprehensive signal quality validation.
    
    Runs all statistical tests and returns comprehensive report.
    
    Args:
        buy_returns: Returns from BUY signals
        hold_returns: Returns from HOLD signals (optional)
        benchmark_returns: Benchmark returns (optional)
        risk_free_rate: Risk-free rate for Sharpe calculation
    
    Returns:
        Dictionary with all test results and overall assessment
    """
    results = {
        "n_buy_signals": len(buy_returns),
        "n_hold_signals": len(hold_returns) if hold_returns else 0,
    }
    
    # Hit rate test
    buy_hits = sum(1 for r in buy_returns if r > 0)
    results["hit_rate_test"] = binomial_test_hit_rate(buy_hits, len(buy_returns))
    
    # Bootstrap CI for mean return
    results["bootstrap_ci"] = bootstrap_confidence_interval(buy_returns)
    
    # Sharpe ratio
    results["sharpe_ratio"] = calculate_sharpe_ratio(buy_returns, risk_free_rate)
    
    # Max drawdown
    results["max_drawdown"] = calculate_max_drawdown(buy_returns)
    
    # Information ratio if benchmark provided
    if benchmark_returns and len(benchmark_returns) == len(buy_returns):
        results["information_ratio"] = calculate_information_ratio(buy_returns, benchmark_returns)
    
    # Compare with HOLD if provided
    if hold_returns and len(hold_returns) == len(buy_returns):
        results["vs_hold_t_test"] = paired_t_test(hold_returns, buy_returns)
    
    # Overall assessment
    hit_rate = results["hit_rate_test"].get("hit_rate", 0)
    sharpe = results["sharpe_ratio"].get("sharpe_ratio", 0)
    max_dd = results["max_drawdown"].get("max_drawdown", 0)
    
    # Quality thresholds (industry standards)
    quality_assessment = []
    
    if hit_rate >= 0.55:
        quality_assessment.append("Hit rate >= 55% (good)")
    elif hit_rate >= 0.50:
        quality_assessment.append("Hit rate >= 50% (acceptable)")
    else:
        quality_assessment.append("Hit rate < 50% (needs improvement)")
    
    if sharpe >= 1.0:
        quality_assessment.append("Sharpe >= 1.0 (good)")
    elif sharpe >= 0.5:
        quality_assessment.append("Sharpe >= 0.5 (acceptable)")
    else:
        quality_assessment.append("Sharpe < 0.5 (needs improvement)")
    
    if max_dd <= -20:
        quality_assessment.append("Max drawdown <= -20% (acceptable)")
    elif max_dd <= -30:
        quality_assessment.append("Max drawdown <= -30% (moderate risk)")
    else:
        quality_assessment.append("Max drawdown > -30% (high risk)")
    
    results["quality_assessment"] = quality_assessment
    results["overall_quality"] = "GOOD" if len([a for a in quality_assessment if "good" in a.lower()]) >= 2 else "ACCEPTABLE" if len([a for a in quality_assessment if "acceptable" in a.lower()]) >= 2 else "NEEDS_IMPROVEMENT"
    
    return results
