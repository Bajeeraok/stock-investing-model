"use client";

import { useMemo, useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { clsx } from "clsx";
import type { DecisionMode } from "@/lib/decisionMode";
import type { InvestorDecisionSummary } from "./InvestorDecisionSummary";
import {
  buildExecutionPlanViewModel,
  stageActChipClass,
  statusTone,
} from "./executionPlanModel";

export function ExecutionPlanRationale({
  summary,
  currentPrice,
  companyName,
  sector,
  mode = "swing",
  variant = "panel",
  showEvidence = true,
  showTickerLine = true,
  collapsible = false,
  defaultOpen = true,
  hideValuationHeader = false,
  hideBuyStages = false,
}: {
  summary: InvestorDecisionSummary;
  currentPrice: number;
  companyName?: string | null;
  sector?: string | null;
  mode?: DecisionMode;
  /** panel = full gradient block; deck = nested inside DecisionDeck */
  variant?: "panel" | "deck";
  showEvidence?: boolean;
  showTickerLine?: boolean;
  collapsible?: boolean;
  defaultOpen?: boolean;
  hideValuationHeader?: boolean;
  hideBuyStages?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const [evidenceOpen, setEvidenceOpen] = useState({
    market: false,
    chart: false,
    flow: false,
    business: false,
  });

  const vm = useMemo(
    () => buildExecutionPlanViewModel(summary, currentPrice, mode),
    [summary, currentPrice, mode],
  );

  if (!vm) return null;

  const { one_answer } = summary;
  const { fair_value } = summary;
  const body = (
    <>
      {!hideValuationHeader && (
        <>
      <div className="flex items-center justify-between gap-2 flex-wrap mb-2">
        <span
          className={clsx(
            "text-sm font-medium cursor-help",
            vm.assessmentPct >= 0 ? "text-emerald-300" : "text-red-300",
          )}
          title="Undervalued / overvalued = price vs model fair value. Verdict can still be WATCH if timing gates are not cleared."
        >
          {Math.abs(vm.assessmentPct).toFixed(1)}% {vm.assessmentPct >= 0 ? "undervalued" : "overvalued"}
        </span>
      </div>
      <p
        className="text-xs text-slate-500 leading-snug mb-2 cursor-help"
        title="Cheap vs fair value answers margin of safety; verdict answers whether to size in today."
      >
        You can be undervalued on this line and still see WATCH or REDUCE elsewhere — value without timing yet,
        not a broken model.
      </p>
        </>
      )}

      {vm.confidenceNearlyThere && vm.confidenceNearlyThereCopy && (
        <div
          className="mb-3 rounded-xl border-2 border-violet-400/60 bg-violet-950/45 px-3 py-2.5 shadow-[0_0_22px_-6px_rgba(167,139,250,0.45)] ring-1 ring-violet-400/25"
          role="status"
        >
          <p className="text-sm font-semibold text-violet-200 mb-0.5 flex items-center gap-1.5">
            <span className="inline-block h-1.5 w-1.5 rounded-full bg-violet-400 animate-pulse" />
            Nearly there — confidence gate
          </p>
          <p className="text-sm text-violet-100/95 leading-snug">{vm.confidenceNearlyThereCopy}</p>
        </div>
      )}

      {vm.momentumTension?.active && (
        <div className="mb-3 rounded-xl border border-cyan-500/45 bg-cyan-950/35 px-3 py-2.5 ring-1 ring-cyan-400/20" role="note">
          <p className="text-sm font-semibold text-cyan-200 mb-1">{vm.momentumTension.headline}</p>
          <p className="text-sm text-cyan-100/90 leading-snug">{vm.momentumTension.detail}</p>
        </div>
      )}

      {vm.athDisconnect?.active && (
        <div className="mb-3 rounded-xl border border-amber-500/45 bg-amber-950/30 px-3 py-2.5 ring-1 ring-amber-400/20" role="note">
          <p className="text-sm font-semibold text-amber-200 mb-1">{vm.athDisconnect.headline}</p>
          <p className="text-sm text-amber-100/90 leading-snug">{vm.athDisconnect.detail}</p>
        </div>
      )}

      {showTickerLine && (
        <p className="text-sm text-slate-400 mb-1">
          {companyName || "This ticker"}
          {sector ? ` · ${sector}` : ""} · ${currentPrice > 0 ? `$${currentPrice.toFixed(2)}` : "—"} · Fair value $
          {fair_value.toFixed(2)}
        </p>
      )}

      {vm.whyBullets.length > 0 && (
        <div className="mt-3 rounded-lg border border-slate-600/70 bg-slate-900/40 px-3 py-2.5">
          <p className="text-xs text-slate-500 uppercase tracking-wide font-semibold mb-1.5">Why this call</p>
          <ul className="space-y-1.5 text-sm text-slate-200 leading-snug">
            {vm.whyBullets.map((line, i) => (
              <li key={i} className="flex items-start gap-2">
                <span className="text-emerald-400 shrink-0 mt-0.5">›</span>
                <span>{line}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {vm.triggerText && (
        <div className="mt-3 rounded-lg border border-sky-500/35 bg-sky-950/25 px-3 py-2.5">
          <p className="text-sm text-sky-100 leading-snug">
            <span className="font-semibold text-sky-200">Your trigger: </span>
            {vm.triggerText}
          </p>
          {vm.actWhenLine && (
            <p className="text-xs text-slate-400 mt-1.5 leading-snug">
              <span className="text-slate-500 font-medium">Horizon act-when: </span>
              {vm.actWhenLine}
            </p>
          )}
        </div>
      )}

      {vm.executionBullets.length > 0 && (
        <div className="mt-3 rounded-lg border border-emerald-500/25 bg-emerald-950/20 px-3 py-2.5">
          <p className="text-xs text-emerald-300/80 uppercase tracking-wide font-semibold mb-1.5">Action plan</p>
          <ol className="space-y-1.5 text-sm text-slate-200 leading-snug list-none">
            {vm.executionBullets.map((line, i) => (
              <li key={i} className="flex items-start gap-2">
                <span className="text-emerald-400 font-bold shrink-0 w-4 text-center">{i + 1}</span>
                <span>{line}</span>
              </li>
            ))}
          </ol>
        </div>
      )}

      {!hideBuyStages && vm.buyStages.length > 0 && (
        <div className="mt-3 rounded-lg border border-slate-600/70 bg-slate-900/40 px-3 py-2.5">
          <p className="text-xs text-slate-500 uppercase tracking-wide font-semibold mb-2">Staged buy timeline</p>
          <div className="space-y-2">
            {vm.buyStages.map((s) => (
              <div
                key={s.timeline_key}
                className={clsx(
                  "text-sm",
                  s.is_gap_row && "rounded-lg border border-amber-500/25 bg-amber-950/20 px-2 py-1.5 -mx-1",
                )}
              >
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="shrink-0 w-24 text-slate-400 font-medium">{s.label}</span>
                  <span className={clsx("shrink-0 px-1.5 py-0.5 rounded text-xs font-medium", stageActChipClass(s.when_to_act))}>
                    {s.when_to_act}
                  </span>
                  <span className="font-mono text-slate-300">
                    ${s.price_zone_low.toFixed(2)}–${s.price_zone_high.toFixed(2)}
                  </span>
                  {s.position_pct > 0 && <span className="text-slate-500">{s.position_pct}%</span>}
                </div>
                {s.bridge_zone_low != null && s.bridge_zone_high != null && (
                  <p className="text-[11px] text-cyan-300/90 font-mono mt-0.5 ml-24 sm:ml-0">
                    Bridge ${s.bridge_zone_low.toFixed(2)}–${s.bridge_zone_high.toFixed(2)}
                  </p>
                )}
                {s.catch_levels && s.catch_levels.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-1">
                    {s.catch_levels.map((lv) => (
                      <span
                        key={lv.id}
                        className="text-[10px] font-mono tabular-nums px-1.5 py-0.5 rounded border border-emerald-500/30 text-emerald-200/90"
                        title={lv.label}
                      >
                        ${lv.price.toFixed(2)}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {showEvidence && (
        <div className="mt-3 rounded-xl border border-slate-700/80 bg-slate-900/50 overflow-hidden divide-y divide-slate-700/60">
          {(
            [
              { key: "market" as const, label: "Market structure", status: vm.marketStatus, summary: vm.marketSummary, expanded: evidenceOpen.market },
              { key: "chart" as const, label: "Chart & momentum", status: vm.chartStatus, summary: vm.chartSummary, expanded: evidenceOpen.chart },
              { key: "flow" as const, label: "Smart money", status: vm.flowStatus, summary: vm.flowSummary, expanded: evidenceOpen.flow, extra: ". Keep sizing staged while transition risk remains." },
              { key: "business" as const, label: "Business & news", status: vm.businessStatus, summary: vm.businessSummary, expanded: evidenceOpen.business },
            ] as const
          ).map((row) => (
            <div key={row.key}>
              <button
                type="button"
                onClick={() => setEvidenceOpen((s) => ({ ...s, [row.key]: !s[row.key] }))}
                className="w-full px-3.5 py-2.5 text-left hover:bg-slate-800/70 flex items-center justify-between gap-2"
              >
                <div className="min-w-0">
                  <span className="text-xs text-slate-200 flex items-center gap-2">
                    {row.label}
                    <span className={clsx("text-xs px-1.5 py-0.5 rounded border", statusTone(row.status))}>
                      {row.status}
                    </span>
                  </span>
                  <p className="text-xs text-slate-500 mt-0.5 truncate">{row.summary}</p>
                </div>
                {row.expanded ? (
                  <ChevronDown className="h-3.5 w-3.5 text-slate-500 shrink-0" />
                ) : (
                  <ChevronRight className="h-3.5 w-3.5 text-slate-500 shrink-0" />
                )}
              </button>
              {row.expanded && (
                <p className="px-3.5 pb-2.5 text-sm text-slate-300 bg-slate-950/40 leading-snug">
                  {row.summary}
                  {"extra" in row && row.extra ? row.extra : ""}
                </p>
              )}
            </div>
          ))}
        </div>
      )}

      {one_answer?.bottom_line && variant === "deck" && (
        <p className="text-sm text-slate-200 leading-snug border-t border-slate-600/60 pt-2 mt-3">
          <span className="font-semibold text-emerald-200/95">Bottom line: </span>
          {one_answer.bottom_line}
        </p>
      )}
    </>
  );

  if (collapsible && !open) {
    return (
      <div className={variant === "panel" ? "border-b border-slate-700/80 bg-slate-900/30" : undefined}>
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="w-full flex items-center justify-between gap-2 px-4 py-3 text-left hover:bg-slate-800/40 transition-colors"
        >
          <span className="text-sm text-slate-400 uppercase tracking-wide">Execution plan & rationale</span>
          <ChevronRight className="h-4 w-4 text-slate-500" />
        </button>
      </div>
    );
  }

  if (collapsible) {
    return (
      <div className={variant === "panel" ? "border-b border-slate-700/80" : undefined}>
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="w-full flex items-center justify-between gap-2 px-4 py-3 text-left hover:bg-slate-800/40 transition-colors border-b border-slate-700/50"
        >
          <span className="text-sm text-slate-400 uppercase tracking-wide">Execution plan & rationale</span>
          <ChevronDown className="h-4 w-4 text-slate-500" />
        </button>
        <div
          className={clsx(
            variant === "panel" &&
              "p-4 border-b border-slate-700/80 bg-gradient-to-br from-emerald-500/10 via-slate-900/60 to-slate-900/40",
            variant === "deck" && "pt-3 border-t border-slate-600/80",
          )}
        >
          {body}
        </div>
      </div>
    );
  }

  return (
    <div
      className={clsx(
        variant === "panel" &&
          "p-4 border-b border-slate-700/80 bg-gradient-to-br from-emerald-500/10 via-slate-900/60 to-slate-900/40",
        variant === "deck" && "pt-3 border-t border-slate-600/80",
      )}
    >
      {body}
    </div>
  );
}
