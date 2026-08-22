/**
 * Actionable (confidence-adjusted) score — mirrors backend/signals/actionable_score.py.
 * Headline number should answer "how much should I act today?", not raw setup beauty.
 */
export const CONFIDENCE_GATE_TARGET_PCT = 55;
export const STALE_PRICE_HOURS_DEFAULT = 36;

export type ActionableScoreFactors = {
  gates_passed: number;
  gates_total: number;
  gate_multiplier: number;
  fused_confidence_pct: number | null;
  confidence_target_pct: number;
  confidence_multiplier: number;
  ml_calibration_factor: number;
  price_age_hours: number | null;
  freshness_multiplier: number;
};

export type ActionableScoreBlock = {
  setup_quality: number | null;
  actionable: number | null;
  stale: boolean;
  suppressed: boolean;
  factors: ActionableScoreFactors;
  note: string;
};

export function computeActionableScore(input: {
  setupQuality: number | null | undefined;
  gatesPassed: number | null | undefined;
  gatesTotal?: number;
  fusedConfidencePct?: number | null;
  confidenceTargetPct?: number;
  priceAgeHours?: number | null;
  staleThresholdHours?: number;
  mlCalibrationFactor?: number | null;
}): ActionableScoreBlock {
  const setupRaw = input.setupQuality;
  if (setupRaw == null || Number.isNaN(Number(setupRaw))) {
    return {
      setup_quality: null,
      actionable: null,
      stale: false,
      suppressed: false,
      factors: {
        gates_passed: 0,
        gates_total: input.gatesTotal ?? 4,
        gate_multiplier: 1,
        fused_confidence_pct: null,
        confidence_target_pct: input.confidenceTargetPct ?? CONFIDENCE_GATE_TARGET_PCT,
        confidence_multiplier: 1,
        ml_calibration_factor: 1,
        price_age_hours: null,
        freshness_multiplier: 1,
      },
      note: "Setup quality unavailable",
    };
  }

  const setup = Math.max(0, Math.min(100, Number(setupRaw)));
  const total = Math.max(1, input.gatesTotal ?? 4);
  const passed = Math.max(0, Math.min(total, input.gatesPassed ?? total));
  const gateMult = passed / total;

  const conf = input.fusedConfidencePct;
  const target = Math.max(1, input.confidenceTargetPct ?? CONFIDENCE_GATE_TARGET_PCT);
  const confMult =
    conf == null || Number.isNaN(Number(conf))
      ? 1
      : Math.min(1, Math.max(0.05, Number(conf) / target));

  let cal = input.mlCalibrationFactor ?? 1;
  if (cal == null || Number.isNaN(Number(cal))) cal = 1;
  cal = Math.min(1, Math.max(0.5, Number(cal)));

  const age = input.priceAgeHours;
  const thresh = input.staleThresholdHours ?? STALE_PRICE_HOURS_DEFAULT;
  const stale = age != null && !Number.isNaN(Number(age)) && Number(age) > thresh;
  const freshnessMult = stale ? 0 : 1;
  const suppressed = stale;

  const raw = setup * gateMult * confMult * cal * freshnessMult;
  const actionable = suppressed ? null : Math.round(Math.max(0, Math.min(100, raw)) * 10) / 10;

  const parts = [
    `setup ${Math.round(setup)}`,
    `gates ${passed}/${total} (×${gateMult.toFixed(2)})`,
    conf == null
      ? `confidence n/a (×${confMult.toFixed(2)})`
      : `fused ${Math.round(Number(conf))}% / target ${Math.round(target)}% (×${confMult.toFixed(2)})`,
  ];
  if (cal < 0.999) parts.push(`ML cal ×${cal.toFixed(2)}`);
  if (stale) parts.push(`STALE price (~${Math.round(Number(age))}h) — score suppressed`);

  return {
    setup_quality: Math.round(setup * 10) / 10,
    actionable,
    stale,
    suppressed,
    factors: {
      gates_passed: passed,
      gates_total: total,
      gate_multiplier: Math.round(gateMult * 1000) / 1000,
      fused_confidence_pct: conf == null ? null : Math.round(Number(conf) * 10) / 10,
      confidence_target_pct: target,
      confidence_multiplier: Math.round(confMult * 1000) / 1000,
      ml_calibration_factor: Math.round(cal * 1000) / 1000,
      price_age_hours: age == null ? null : Math.round(Number(age) * 100) / 100,
      freshness_multiplier: freshnessMult,
    },
    note: parts.join(" · "),
  };
}
