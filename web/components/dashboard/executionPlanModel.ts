import type { DecisionMode } from "@/lib/decisionMode";
import { primaryHorizonFromMode } from "@/lib/decisionMode";
import type { InvestorDecisionSummary, HorizonSignalPayload } from "./InvestorDecisionSummary";
import type { RetailActionPayload } from "./retailActionUX";

export type EvidenceStatus = "Constructive" | "Neutral" | "Cautionary";

export type BuyStagePreview = {
  timeline_key: string;
  label: string;
  when_to_act: string;
  price_zone_low: number;
  price_zone_high: number;
  position_pct: number;
  bridge_zone_low?: number;
  bridge_zone_high?: number;
  catch_levels?: Array<{ id: string; label: string; price: number; role?: string }>;
  is_gap_row?: boolean;
  condition?: string;
  sync_note?: string;
};

export type ExecutionPlanViewModel = {
  assessmentPct: number;
  whyBullets: string[];
  triggerText: string | null;
  actWhenLine: string | null;
  executionBullets: string[];
  buyStages: BuyStagePreview[];
  marketStatus: EvidenceStatus;
  marketSummary: string;
  chartStatus: EvidenceStatus;
  chartSummary: string;
  flowStatus: EvidenceStatus;
  flowSummary: string;
  businessStatus: EvidenceStatus;
  businessSummary: string;
  confidenceNearlyThere: boolean;
  confidenceNearlyThereCopy: string | null;
  momentumTension: InvestorDecisionSummary["one_answer"] extends infer O
    ? O extends { momentum_valuation_tension?: infer M }
      ? M
      : null
    : null;
  athDisconnect: InvestorDecisionSummary["one_answer"] extends infer O
    ? O extends { ath_macro_regime_disconnect?: infer A }
      ? A
      : null
    : null;
};

export type NextTriggerInput = RetailActionPayload["next_trigger"] | string | null | undefined;

export function formatNextTriggerText(trigger: NextTriggerInput): string | null {
  if (trigger == null) return null;
  if (typeof trigger === "string") {
    const t = trigger.trim();
    return t || null;
  }
  const parts: string[] = [];
  if (trigger.headline?.trim()) parts.push(trigger.headline.trim());
  if (trigger.detail?.trim()) parts.push(trigger.detail.trim());
  if (trigger.estimated_days != null && trigger.estimated_days > 0) {
    parts.push(`~${trigger.estimated_days}d`);
  }
  return parts.length ? parts.join(" — ") : null;
}

export function triggersDiffer(a: string | null, b: string | null): boolean {
  if (!a || !b) return Boolean(a) !== Boolean(b);
  const na = a.trim().toLowerCase();
  const nb = b.trim().toLowerCase();
  if (na === nb) return false;
  return !(na.includes(nb) || nb.includes(na));
}

function prioritizeBullets(lines: string[], maxBullets = 3): string[] {
  const priorityKeywords = [
    "pulls back",
    "entry",
    "stop",
    "scale",
    "powder",
    "partial",
    "loses",
    "reassess",
  ];
  const score = (line: string): number => {
    const lower = line.toLowerCase();
    const idx = priorityKeywords.findIndex((k) => lower.includes(k));
    return idx === -1 ? 99 : idx;
  };
  return [...lines].sort((a, b) => score(a) - score(b)).slice(0, maxBullets);
}

function horizonForMode(
  mode: DecisionMode,
  horizons: InvestorDecisionSummary["horizons"],
): HorizonSignalPayload {
  const key = primaryHorizonFromMode(mode);
  return key === "short" ? horizons.short : key === "medium" ? horizons.medium : horizons.long;
}

const CONFIDENCE_GATE_TARGET = 55;

export function buildExecutionPlanViewModel(
  summary: InvestorDecisionSummary,
  currentPrice: number,
  mode: DecisionMode = "swing",
): ExecutionPlanViewModel | null {
  const { one_answer, horizons, fair_value, overall_verdict, pattern_score, regime_bull_pct, trade_roadmap, retail_action } =
    summary;
  if (!one_answer) return null;

  const short = horizons.short;
  const medium = horizons.medium;
  const long = horizons.long;
  const primary = horizonForMode(mode, horizons);

  const assessmentPct =
    currentPrice > 0 && fair_value > 0 ? ((fair_value - currentPrice) / fair_value) * 100 : 0; // MOS vs FV

  const tldr = trade_roadmap?.tldr ?? null;
  const dual = tldr?.dual_signal ?? null;
  const confidenceBand = tldr?.model_confidence_band ?? null;
  const confidenceBandMatch = confidenceBand?.match(/(\d+)\s*-\s*(\d+)%?/);
  const confidenceBandMid =
    confidenceBandMatch && confidenceBandMatch[1] && confidenceBandMatch[2]
      ? (Number(confidenceBandMatch[1]) + Number(confidenceBandMatch[2])) / 2
      : (summary.model_confidence_pct ?? tldr?.model_confidence_pct ?? null);

  const marketStatus: EvidenceStatus =
    dual?.display_mode === "pre_flip_watch"
      ? "Cautionary"
      : overall_verdict === "STRONG BUY" || overall_verdict === "BUY"
        ? "Constructive"
        : overall_verdict === "WATCH"
          ? "Neutral"
          : "Cautionary";

  const chartStatus: EvidenceStatus =
    (pattern_score ?? 50) >= 65 && (short.verdict === "BUY" || short.verdict === "STRONG BUY")
      ? "Constructive"
      : (pattern_score ?? 50) < 45 || short.verdict === "WAIT"
        ? "Cautionary"
        : "Neutral";

  const flowStatus: EvidenceStatus =
    (medium.ml_prob ?? 50) >= 60 ? "Constructive" : (medium.ml_prob ?? 50) < 40 ? "Cautionary" : "Neutral";

  const businessStatus: EvidenceStatus =
    long.verdict === "BUY" || long.verdict === "STRONG BUY"
      ? "Constructive"
      : long.verdict === "WATCH"
        ? "Neutral"
        : "Cautionary";

  const ptsToConfidenceGate =
    confidenceBandMid != null ? CONFIDENCE_GATE_TARGET - Number(confidenceBandMid) : null;
  const confidenceNearlyThere =
    ptsToConfidenceGate != null && ptsToConfidenceGate > 0 && ptsToConfidenceGate <= 10;

  const nextTrigger = formatNextTriggerText(retail_action?.next_trigger ?? one_answer.next_trigger ?? null);
  const actWhenLine = primary.trigger_buy?.trim() || null;
  const triggerText =
    nextTrigger && triggersDiffer(nextTrigger, actWhenLine)
      ? nextTrigger
      : nextTrigger || actWhenLine;

  const stages = trade_roadmap?.buy_roadmap;
  const buyStages: BuyStagePreview[] = Array.isArray(stages)
    ? stages
        .filter((s) => s.price_zone_low != null && s.price_zone_high != null)
        .slice(0, 6)
        .map((s) => ({
          timeline_key: s.timeline_key,
          label: s.label,
          when_to_act: s.when_to_act,
          price_zone_low: Number(s.price_zone_low),
          price_zone_high: Number(s.price_zone_high),
          position_pct: s.position_pct ?? 0,
          bridge_zone_low:
            s.bridge_zone_low != null && s.bridge_zone_low !== undefined
              ? Number(s.bridge_zone_low)
              : undefined,
          bridge_zone_high:
            s.bridge_zone_high != null && s.bridge_zone_high !== undefined
              ? Number(s.bridge_zone_high)
              : undefined,
          catch_levels: Array.isArray(s.catch_levels)
            ? s.catch_levels.map((l) => ({
                id: String(l.id),
                label: String(l.label),
                price: Number(l.price),
                role: l.role,
              }))
            : undefined,
          is_gap_row: Boolean(s.is_gap_row),
          condition: s.condition ? String(s.condition) : undefined,
          sync_note: s.sync_note ? String(s.sync_note) : undefined,
        }))
    : [];

  return {
    assessmentPct,
    whyBullets: (Array.isArray(one_answer.why_this_call) ? one_answer.why_this_call : []).slice(0, 2),
    triggerText,
    actWhenLine:
      actWhenLine && triggerText && triggersDiffer(actWhenLine, triggerText) ? actWhenLine : null,
    executionBullets: prioritizeBullets(
      Array.isArray(one_answer.execution_plan_lines) ? one_answer.execution_plan_lines : [],
      3,
    ),
    buyStages,
    marketStatus,
    marketSummary: dual?.bridge_note || tldr?.strategy || "Regime context is mixed.",
    chartStatus,
    chartSummary: `Pattern ${Math.round(Number(pattern_score ?? 50))}/100 · Short ${short.verdict || "N/A"} · ML ${Number(medium.ml_prob ?? 0).toFixed(0)}%`,
    flowStatus,
    flowSummary: `Confidence ${medium.conviction || "mixed"} / ${long.conviction || "mixed"}`,
    businessStatus,
    businessSummary: `Long verdict ${long.verdict || "N/A"} · FV gap ${assessmentPct >= 0 ? "+" : ""}${assessmentPct.toFixed(1)}%`,
    confidenceNearlyThere,
    confidenceNearlyThereCopy: confidenceNearlyThere
      ? `Fused model confidence is ${Math.round(Number(confidenceBandMid))}% vs ${CONFIDENCE_GATE_TARGET}% used here — you're within about ${Math.ceil(Number(ptsToConfidenceGate))} point${Math.ceil(Number(ptsToConfidenceGate)) === 1 ? "" : "s"}. Fresh sessions often move this; worth a quick revisit.`
      : null,
    momentumTension: one_answer.momentum_valuation_tension ?? null,
    athDisconnect: one_answer.ath_macro_regime_disconnect ?? null,
  };
}

export function stageActChipClass(whenToAct: string): string {
  const lower = whenToAct.toLowerCase();
  if (lower.includes("add") || lower.includes("start")) {
    return "bg-emerald-500/15 text-emerald-300 border border-emerald-500/30";
  }
  if (lower.includes("watch")) {
    return "bg-amber-500/10 text-amber-300 border border-amber-500/30";
  }
  return "bg-slate-700/40 text-slate-400 border border-slate-600/60";
}

export function statusTone(status: EvidenceStatus): string {
  return status === "Constructive"
    ? "text-emerald-300 bg-emerald-500/10 border-emerald-500/30"
    : status === "Cautionary"
      ? "text-amber-200 bg-amber-500/10 border-amber-500/30"
      : "text-slate-300 bg-slate-700/40 border-slate-600/60";
}

export function catchLevelsFingerprint(
  levels?: BuyStagePreview["catch_levels"] | null,
): string {
  if (!levels?.length) return "";
  return levels.map((l) => `${l.id}:${l.price.toFixed(4)}`).join("|");
}

export function resolveSharedCatchLevels(stages: BuyStagePreview[]): {
  shared: BuyStagePreview["catch_levels"] | null;
  uniform: boolean;
} {
  const withLevels = stages.filter((s) => s.catch_levels && s.catch_levels.length > 0);
  if (withLevels.length === 0) return { shared: null, uniform: true };
  const fp0 = catchLevelsFingerprint(withLevels[0].catch_levels);
  const uniform = withLevels.every((s) => catchLevelsFingerprint(s.catch_levels) === fp0);
  return {
    shared: uniform ? withLevels[0].catch_levels ?? null : null,
    uniform,
  };
}

export function resolveSharedBridgeZone(stages: BuyStagePreview[]): {
  uniform: boolean;
  low: number | null;
  high: number | null;
} {
  const withBridge = stages.filter(
    (s) => s.bridge_zone_low != null && s.bridge_zone_high != null,
  );
  if (withBridge.length === 0) return { uniform: true, low: null, high: null };
  const lo = withBridge[0].bridge_zone_low!;
  const hi = withBridge[0].bridge_zone_high!;
  const uniform = withBridge.every(
    (s) => s.bridge_zone_low === lo && s.bridge_zone_high === hi,
  );
  return { uniform, low: uniform ? lo : null, high: uniform ? hi : null };
}

/** Border tint when catch levels differ per watch period. */
export function periodCatchLevelTone(timelineKey: string): string {
  if (timelineKey === "today" || timelineKey === "immediate") {
    return "border-cyan-500/35 bg-cyan-950/20";
  }
  if (timelineKey.includes("days") || timelineKey === "short_term") {
    return "border-violet-500/35 bg-violet-950/20";
  }
  if (timelineKey.includes("week")) {
    return "border-emerald-500/35 bg-emerald-950/20";
  }
  return "border-amber-500/30 bg-amber-950/15";
}
