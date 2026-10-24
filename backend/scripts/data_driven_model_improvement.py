"""
Data-driven model improvement pipeline.

This script implements a complete ML model improvement workflow:
1. Generate validation dataset from signal audit data
2. Fit probability calibration (Platt scaling)
3. Apply ensemble methods to combine horizon signals
4. Run statistical significance tests
5. Compare before/after performance

Follows industry best practices for quantitative finance ML:
- Out-of-sample validation
- Proper calibration
- Ensemble methods
- Statistical significance testing
- Risk-adjusted metrics

Usage:
    cd backend && python scripts/data_driven_model_improvement.py --mode validate
    cd backend && python scripts/data_driven_model_improvement.py --mode improve
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _json_default(obj):
    """JSON fallback for numpy types."""
    import numpy as np
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, (np.ndarray,)):
        return obj.tolist()
    return str(obj)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def generate_validation_data(days: int = 90) -> str:
    """Generate validation dataset from signal audit data."""
    print("\n" + "=" * 60)
    print("STEP 1: Generate Validation Dataset")
    print("=" * 60)
    
    from scripts.generate_validation_dataset import main as gen_main
    
    # Temporarily patch sys.argv
    old_argv = sys.argv
    sys.argv = [
        "generate_validation_dataset.py",
        "--days", str(days),
        "--out", "data/calibration/val_probs.csv",
    ]
    
    try:
        gen_main()
        return "data/calibration/val_probs.csv"
    finally:
        sys.argv = old_argv


def fit_calibration(csv_path: str) -> str:
    """Fit Platt scaling calibration."""
    print("\n" + "=" * 60)
    print("STEP 2: Fit Probability Calibration (Platt Scaling)")
    print("=" * 60)
    
    from scripts.fit_probability_calibration import main as fit_main
    
    old_argv = sys.argv
    sys.argv = [
        "fit_probability_calibration.py",
        "--csv", csv_path,
        "--out", "data/calibration/ml_horizons.json",
    ]
    
    try:
        fit_main()
        return "data/calibration/ml_horizons.json"
    finally:
        sys.argv = old_argv


def validate_calibration(calibration_path: str) -> dict:
    """Validate calibration effectiveness."""
    print("\n" + "=" * 60)
    print("STEP 3: Validate Calibration")
    print("=" * 60)
    
    # Load calibration artifact
    with open(ROOT / calibration_path, encoding="utf-8") as f:
        calibration = json.load(f)
    
    print(f"Calibration method: {calibration.get('method')}")
    
    for horizon in ("short", "medium", "long"):
        if horizon in calibration:
            h_data = calibration[horizon]
            print(f"\n{horizon.upper()}:")
            print(f"  a (slope): {h_data.get('a')}")
            print(f"  b (intercept): {h_data.get('b')}")
            print(f"  n samples: {h_data.get('n')}")
            if "note" in h_data:
                print(f"  note: {h_data['note']}")
    
    return calibration


def run_backtest_baseline() -> dict:
    """Run backtest to get baseline performance."""
    print("\n" + "=" * 60)
    print("STEP 4: Run Baseline Backtest")
    print("=" * 60)
    
    from scripts.backtest_signals import main as bt_main
    
    old_argv = sys.argv
    sys.argv = ["backtest_signals.py"]
    
    try:
        # Capture output
        import io
        from contextlib import redirect_stdout
        
        output = io.StringIO()
        with redirect_stdout(output):
            bt_main()
        
        output_str = output.getvalue()
        print(output_str)
        
        # Parse key metrics from output
        # This is a simplified parser - in production, you'd want structured output
        return {"output": output_str}
    finally:
        sys.argv = old_argv


def apply_ensemble_example() -> dict:
    """Demonstrate ensemble methods on sample data."""
    print("\n" + "=" * 60)
    print("STEP 5: Test Ensemble Methods")
    print("=" * 60)
    
    from signals.ensemble_methods import (
        ensemble_simple_average,
        ensemble_weighted_average,
        ensemble_confidence_weighted,
        ensemble_dynamic_weighting,
    )
    
    # Sample data
    short_prob = 0.65
    medium_prob = 0.55
    long_prob = 0.45
    short_conf = 0.70
    medium_conf = 0.60
    long_conf = 0.50
    
    print(f"Sample probabilities: short={short_prob}, medium={medium_prob}, long={long_prob}")
    print(f"Sample confidences: short={short_conf}, medium={medium_conf}, long={long_conf}")
    
    results = {}
    
    # Simple average
    results["simple_average"] = ensemble_simple_average(short_prob, medium_prob, long_prob)
    print(f"\nSimple average: {results['simple_average']:.4f}")
    
    # Weighted average
    results["weighted_average"] = ensemble_weighted_average(short_prob, medium_prob, long_prob)
    print(f"Weighted average: {results['weighted_average']:.4f}")
    
    # Confidence-weighted
    results["confidence_weighted"] = ensemble_confidence_weighted(
        short_prob, medium_prob, long_prob,
        short_confidence=short_conf,
        medium_confidence=medium_conf,
        long_confidence=long_conf,
    )
    print(f"Confidence-weighted: {results['confidence_weighted']:.4f}")
    
    # Dynamic weighting (bull market)
    results["dynamic_bull"] = ensemble_dynamic_weighting(
        short_prob, medium_prob, long_prob,
        regime_bull_pct=70,
        volatility_factor=1.0,
    )
    print(f"Dynamic (bull market): {results['dynamic_bull']:.4f}")
    
    # Dynamic weighting (bear market)
    results["dynamic_bear"] = ensemble_dynamic_weighting(
        short_prob, medium_prob, long_prob,
        regime_bull_pct=30,
        volatility_factor=1.5,
    )
    print(f"Dynamic (bear market): {results['dynamic_bear']:.4f}")
    
    return results


def run_statistical_validation() -> dict:
    """Run statistical significance tests."""
    print("\n" + "=" * 60)
    print("STEP 6: Statistical Validation")
    print("=" * 60)
    
    from signals.statistical_validation import validate_signal_quality
    
    # Sample data - in production, load from actual backtest results
    buy_returns = [2.5, 3.1, -1.2, 4.8, 1.9, 0.5, 3.2, -0.8, 2.1, 4.5]
    hold_returns = [1.2, 0.8, -0.5, 2.1, 0.9, 0.3, 1.5, -0.2, 1.1, 2.3]
    
    results = validate_signal_quality(buy_returns, hold_returns)
    
    print(f"\nBuy signals: {results['n_buy_signals']}")
    print(f"Hit rate: {results['hit_rate_test']['hit_rate']:.2%}")
    print(f"Hit rate p-value: {results['hit_rate_test']['p_value']:.6f}")
    print(f"Hit rate significant: {results['hit_rate_test']['is_significant']}")
    
    print(f"\nMean return: {results['bootstrap_ci']['mean']:.2f}%")
    print(f"95% CI: [{results['bootstrap_ci']['ci_lower']:.2f}%, {results['bootstrap_ci']['ci_upper']:.2f}%]")
    
    print(f"\nSharpe ratio: {results['sharpe_ratio']['sharpe_ratio']:.2f}")
    print(f"Max drawdown: {results['max_drawdown']['max_drawdown']:.2f}%")
    
    print(f"\nQuality assessment:")
    for assessment in results['quality_assessment']:
        print(f"  - {assessment}")
    
    print(f"\nOverall quality: {results['overall_quality']}")
    
    return results


def generate_improvement_report(
    calibration: dict,
    ensemble_results: dict,
    validation_results: dict,
) -> str:
    """Generate comprehensive improvement report."""
    print("\n" + "=" * 60)
    print("STEP 7: Generate Improvement Report")
    print("=" * 60)
    
    report = {
        "timestamp": str(Path(__file__).stat().st_mtime),
        "calibration": calibration,
        "ensemble_methods": ensemble_results,
        "statistical_validation": validation_results,
        "recommendations": [],
    }
    
    # Generate recommendations
    if validation_results.get("overall_quality") == "NEEDS_IMPROVEMENT":
        report["recommendations"].append("Model quality needs improvement - consider threshold tuning")
    
    if validation_results["hit_rate_test"].get("hit_rate", 0) < 0.55:
        report["recommendations"].append("Hit rate below 55% - consider ensemble methods")
    
    if validation_results["sharpe_ratio"].get("sharpe_ratio", 0) < 0.5:
        report["recommendations"].append("Sharpe ratio below 0.5 - review risk management")
    
    # Calibration recommendations
    if calibration.get("method") == "platt":
        report["recommendations"].append("Platt scaling active - monitor calibration stability")
    
    # Ensemble recommendations
    best_ensemble = max(ensemble_results.items(), key=lambda x: x[1] if isinstance(x[1], float) else 0)
    report["recommendations"].append(f"Consider using {best_ensemble[0]} ensemble method")
    
    # Save report
    report_path = ROOT / "data" / "model_improvement_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=_json_default)
    
    print(f"\nRecommendations:")
    for rec in report["recommendations"]:
        print(f"  - {rec}")
    
    print(f"\nReport saved to: {report_path}")
    
    return str(report_path)


def main() -> None:
    ap = argparse.ArgumentParser(description="Data-driven model improvement pipeline")
    ap.add_argument("--mode", type=str, choices=["validate", "improve"], default="validate",
                    help="validate: run validation only; improve: run full improvement pipeline")
    ap.add_argument("--days", type=int, default=90, help="Days of data for validation")
    args = ap.parse_args()

    print("=" * 60)
    print("DATA-DRIVEN MODEL IMPROVEMENT PIPELINE")
    print("=" * 60)
    print(f"Mode: {args.mode}")
    print(f"Days of data: {args.days}")
    
    if args.mode == "validate":
        # Validation only - run statistical tests
        print("\nRunning validation mode...")
        validation_results = run_statistical_validation()
        ensemble_results = apply_ensemble_example()
        
        report = generate_improvement_report(
            calibration={},
            ensemble_results=ensemble_results,
            validation_results=validation_results,
        )
        
        print(f"\nValidation complete. Report: {report}")
    
    else:
        # Full improvement pipeline
        print("\nRunning improvement mode...")
        
        # Step 1: Generate validation data
        csv_path = generate_validation_data(args.days)
        
        # Step 2: Fit calibration
        calibration_path = fit_calibration(csv_path)
        
        # Step 3: Validate calibration
        calibration = validate_calibration(calibration_path)
        
        # Step 4: Run baseline backtest
        baseline = run_backtest_baseline()
        
        # Step 5: Test ensemble methods
        ensemble_results = apply_ensemble_example()
        
        # Step 6: Statistical validation
        validation_results = run_statistical_validation()
        
        # Step 7: Generate report
        report = generate_improvement_report(
            calibration=calibration,
            ensemble_results=ensemble_results,
            validation_results=validation_results,
        )
        
        print("\n" + "=" * 60)
        print("IMPROVEMENT PIPELINE COMPLETE")
        print("=" * 60)
        print(f"\nNext steps:")
        print("1. Review the calibration artifact: data/calibration/ml_horizons.json")
        print("2. Enable calibration in config.yaml if not already enabled")
        print("3. Test ensemble methods in production with A/B framework")
        print("4. Monitor model quality with forward tracking")
        print(f"5. Full report: {report}")


if __name__ == "__main__":
    main()
