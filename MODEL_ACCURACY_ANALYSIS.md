# Stock Investing Model - Signal Generation & Entry Band Analysis

## Executive Summary

This analysis identifies key improvements and bug fixes needed to make your model more accurate in generating signals and entry bands for all 3 modes: **Scout** (short-term 1m), **Swing** (medium-term 3m), and **Owner** (long-term 6-18m).

## Key Findings

### 1. **Horizon Entry Calculator Issues** (`horizon_entry_calculator.py`)

#### Critical Issues:

**A. Short-Term (Scout) Signal Generation**
- **Line 1494-1501**: Verdict logic uses `pattern_score >= 55` as a hard gate, but this conflicts with documented normal range (27-43 for non-bottom setups)
- **Line 47-48**: RSI thresholds (35 oversold, 65 overbought) may be too strict for momentum names
- **Line 61-66**: Regime upside caps are complex and may dampen legitimate upside in mixed markets

**B. Medium-Term (Swing) Signal Generation**
- **Line 1694-1703**: Verdict requires `ml_prob >= 35` and `regime_bull_pct >= 45` simultaneously - this creates a false negative when one is strong but the other is marginal
- **Line 1672-1675**: Target cap at 1.15x FV may be too restrictive for high-growth names
- **Line 1801-1802**: Harmonization with short-term may create inconsistent bands

**C. Long-Term (Owner) Signal Generation**
- **Line 2154-2164**: Verdict logic has complex nested conditions that may miss valid setups
- **Line 2147-2151**: Regime < 40 warning may be too sensitive
- **Line 125-136**: Tier 2 MOS classification is hardcoded for specific tickers - may miss new stocks

#### Potential Bugs:

1. **Line 1439-1445**: Zone compression logic may over-compress bands for high-volatility stocks
2. **Line 1648-1670**: R/R enforcement may artificially inflate targets
3. **Line 1987-2000**: T1 ceiling cap to swing zone may create gaps

### 2. **Retail Action Payload Issues** (`retail_action_payload.py`)

#### Critical Issues:

**A. Gate Thresholds**
- **Line 31**: `ST_ML_GATE = 25%` - minimum ML probability for short-term may be too low
- **Line 33**: `REGIME_GATE = 60%` - HMM bull threshold may miss valid setups in 50-60% range
- **Line 34**: `CONFIDENCE_GATE = 55%` - confidence gate may be too strict
- **Line 42**: `MOMENTUM_RSI_MAX = 70` - improved from 50, but still may block valid momentum setups

**B. MOS Ladder Logic**
- **Line 64-67**: Default MOS ladder (10%, 18%, 25%) may not be calibrated for current market conditions
- **Line 486-496**: `required_mos_pct()` function adds regime addon that may compound too aggressively

**C. Entry Mode Derivation**
- **Line 768-777**: Hard lock logic may be too aggressive - blocks entry on rich valuation even in bands
- **Line 759**: `VALUATION_GATE_PARTIAL_PCT = 15%` - partial MOS threshold may not allow enough starter positions

### 3. **Signal Reason Summary Issues** (`signal_reason_summary.py`)

#### Critical Issues:

**A. Factor Weighting**
- **Line 128-129**: Blocker weights (30, 45, 40, 20) may not reflect actual importance
- **Line 222-224**: Normalization may over/under-weight certain factors

**B. Persona-Specific Logic**
- **Line 22-25**: Only swing and owner have prefixes - scout gets no special framing
- **Line 372-375**: Momentum warning logic treats owner same as scout, but long-term holders should ignore short-term momentum

## Priority Recommendations

### P0 - Immediate Fixes (High Impact, Low Risk)

1. **Adjust Scout Pattern Score Threshold**
   - Change line 1494 from `pattern_score >= 55` to `pattern_score >= 35`
   - This aligns with documented normal range and reduces false negatives

2. **Relax Swing Verdict Conditions**
   - Change line 1694 from `regime_bull_pct >= 45` to `regime_bull_pct >= 40`
   - Add OR condition: `(ml_prob >= 35 OR regime_bull_pct >= 45)`
   - Reduces false negatives when one signal is strong

3. **Fix Owner Tier 2 MOS Classification**
   - Add dynamic classification based on fundamentals_score > 60 → large_cap_growth
   - Update hardcoded lists to include missing quality stocks

4. **Adjust Gate Thresholds**
   - `REGIME_GATE`: 60% → 55% (line 33)
   - `CONFIDENCE_GATE`: 55% → 50% (line 34)
   - `ST_ML_GATE`: 25% → 30% (line 31) - raise slightly to reduce noise

### P1 - Calibration Improvements (Medium Impact, Medium Risk)

1. **Harmonize RSI Thresholds Across Horizons**
   - Scout: Keep at 35/65 (oversold/overbought)
   - Swing: Use 40/70 for more flexibility
   - Owner: Ignore RSI entirely for valuation focus

2. **Improve MOS Ladder**
   - Test current ladder (10%, 18%, 25%) against historical win rates
   - Consider (8%, 15%, 22%) for current market
   - Add regime addon only in "stormy" conditions

3. **Zone Compression Review**
   - Line 1286-1291: Review max_pct_by_band values
   - Consider making ST tighter (0.12), MT looser (0.35), LT looser (0.50)

4. **R/R Enforcement Logic**
   - Line 1652-1670: Remove artificial inflation of targets
   - Use ATR-based targets more consistently
   - Cap R/R calculation to realistic ranges

### P2 - Architectural Improvements (High Impact, High Risk)

1. **Mode-Specific Gate Logic**
   - Scout: Stricter on momentum, looser on valuation
   - Swing: Balanced across all gates
   - Owner: Strict on valuation, ignore momentum/momentum gates

2. **Dynamic Threshold Adjustment**
   - Adjust thresholds based on VIX/market volatility
   - Higher volatility → looser RSI, tighter ML
   - Lower volatility → tighter RSI, looser ML

3. **Confidence Calibration**
   - Implement Platt scaling for confidence scores
   - Calibrate per-horizon confidence separately
   - Add confidence floor for high-conviction setups

4. **Entry Band Backtesting**
   - Implement touch rate tracking per band
   - Adjust band widths based on historical hit rates
   - Add band quality score (how often bands are reached)

## Specific Bug Fixes

### Bug #1: Scout Pattern Score False Negatives
**Location**: `horizon_entry_calculator.py:1494`
**Issue**: `pattern_score >= 55` blocks valid setups in normal 27-43 range
**Fix**:
```python
# OLD
all_clear = (inp.ml_prob >= ST_MIN_ML_PROB and inp.rsi < ST_RSI_OVERBOUGHT
             and inp.regime_bull_pct >= 40 and inp.pattern_score >= 55 and rr >= ST_MIN_RR)

# NEW
all_clear = (inp.ml_prob >= ST_MIN_ML_PROB and inp.rsi < ST_RSI_OVERBOUGHT
             and inp.regime_bull_pct >= 40 and inp.pattern_score >= 35 and rr >= ST_MIN_RR)
```

### Bug #2: Swing Verdict Over-Strictness
**Location**: `horizon_entry_calculator.py:1694-1703`
**Issue**: Requires both ML and regime to pass simultaneously
**Fix**:
```python
# OLD
if (inp.ml_prob >= MT_MIN_ML_PROB and quality in ("Ideal", "Acceptable")
        and inp.regime_bull_pct >= 45 and rr >= MT_MIN_RR):

# NEW
if (inp.ml_prob >= MT_MIN_ML_PROB and quality in ("Ideal", "Acceptable")
        and (inp.regime_bull_pct >= 40 or inp.ml_prob >= 45) and rr >= MT_MIN_RR):
```

### Bug #3: Owner Tier 2 Classification Gap
**Location**: `horizon_entry_calculator.py:125-163`
**Issue**: Hardcoded lists miss new quality stocks
**Fix**: Add dynamic fallback:
```python
# Add to classify_mos_class after existing checks
if fundamentals_score >= 60 and fundamentals_score < 75:
    return "large_cap_growth"
if fundamentals_score >= 40 and fundamentals_score < 60:
    return "high_quality_defensive"
```

### Bug #4: Gate Threshold Misalignment
**Location**: `retail_action_payload.py:31-34`
**Issue**: Thresholds may be too strict for current market
**Fix**:
```python
# Update _retail_gates_config() defaults
ST_ML_GATE = float(_RG_CFG.get("ml_short_prob_min", 30))  # was 25
REGIME_GATE = float(_RG_CFG.get("regime_bull_pct_min", 55))  # was 60
CONFIDENCE_GATE = float(_RG_CFG.get("confidence_gate_pct", 50))  # was 55
```

## Testing Recommendations

1. **Backtest Signal Accuracy**
   - Run `backend/scripts/backtest_signals.py` for each mode
   - Compare win rates before/after fixes
   - Focus on false negative reduction

2. **Entry Band Touch Rate Analysis**
   - Run `backend/scripts/build_entry_band_touch_rates.py`
   - Identify bands with <10% touch rates
   - Adjust band widths accordingly

3. **Gate Sensitivity Analysis**
   - Test threshold variations ±5%
   - Measure impact on signal count and accuracy
   - Find optimal threshold balance

4. **Mode-Specific Validation**
   - Validate Scout signals with 1-month forward returns
   - Validate Swing signals with 3-month forward returns
   - Validate Owner signals with 12-month forward returns

## Implementation Order

1. **Week 1**: Implement P0 fixes (4 high-impact, low-risk changes)
2. **Week 2**: Test P0 fixes with backtest
3. **Week 3**: Implement P1 calibration improvements
4. **Week 4**: Test P1 improvements
5. **Week 5-6**: Implement P2 architectural changes (if needed)
6. **Week 7**: Comprehensive validation across all modes

## Monitoring Metrics

Track these metrics to validate improvements:

1. **Signal Accuracy**
   - Scout: 1-month win rate target >55%
   - Swing: 3-month win rate target >60%
   - Owner: 12-month win rate target >65%

2. **Entry Band Quality**
   - Touch rate target >25% for all bands
   - False positive rate <15%

3. **Gate Pass Rates**
   - Valuation gate: ~40-60% pass rate
   - Regime gate: ~50-70% pass rate
   - Momentum gate: ~45-65% pass rate
   - ML gate: ~55-75% pass rate

4. **False Negative Reduction**
   - Target: Reduce false negatives by 20%
   - Maintain false positive rate <20%

## Conclusion

The model has a solid foundation but suffers from overly strict thresholds and some hardcoded classifications that reduce signal accuracy. The recommended fixes focus on:

1. **Relaxing strict gates** to reduce false negatives
2. **Making thresholds dynamic** based on market conditions
3. **Improving mode-specific logic** for Scout/Swing/Owner
4. **Adding backtesting** to validate changes

Implementing P0 fixes should yield immediate accuracy improvements with minimal risk. P1 and P2 can be implemented incrementally based on validation results.
