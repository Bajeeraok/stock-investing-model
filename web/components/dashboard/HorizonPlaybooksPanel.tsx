"use client";

import { useEffect, useMemo, useState } from "react";
import { clsx } from "clsx";
import {
  HorizonPlaybookCard,
  type HorizonPlaybookPayload,
  type HorizonPlaybooksBundle,
} from "./HorizonPlaybookCard";
import { PositionIntentChip } from "./PositionIntentChip";
import {
  getPositionIntent,
  primaryHorizonFromIntent,
  type PositionIntent,
} from "@/lib/positionIntent";
import { horizonLabel, primaryHorizonFromMode, type DecisionMode } from "@/lib/decisionMode";
import type { HorizonSignalPayload } from "./InvestorDecisionSummary";

type HorizonKey = "short" | "medium" | "long";

const TAB_META: Record<HorizonKey, { label: string; anchor: string }> = {
  short: { label: "Swing", anchor: "ATR/VWAP band, weeks" },
  medium: { label: "Position build", anchor: "MA50 + earnings band, ~1–3 mo" },
  long: { label: "Thesis & tiers", anchor: "MA200/fair-value tiers, 6–18 mo" },
};

function pickPlaybook(bundle: HorizonPlaybooksBundle, horizon: HorizonKey): HorizonPlaybookPayload | null {
  if (horizon === "short") return bundle.swing?.active ? bundle.swing : null;
  if (horizon === "medium") return bundle.medium?.active ? bundle.medium : null;
  return bundle.long?.active ? bundle.long : null;
}

/** Lines repeated across playbooks — show once above tabs, not in every card. */
function sharedPlaybookContext(playbooks: HorizonPlaybooksBundle): string[] {
  const lines: string[] = [];
  for (const h of ["short", "medium", "long"] as const) {
    const pb = pickPlaybook(playbooks, h);
    for (const line of pb?.setup_narrative ?? []) {
      const t = String(line).trim();
      if (t) lines.push(t);
    }
  }
  const counts = new Map<string, number>();
  for (const line of lines) {
    counts.set(line, (counts.get(line) ?? 0) + 1);
  }
  return Array.from(counts.entries())
    .filter(([, n]) => n >= 2)
    .map(([line]) => line)
    .slice(0, 4);
}

export function HorizonPlaybooksPanel({
  ticker,
  playbooks,
  intent: intentProp,
  onIntentChange,
  decisionMode,
  entryTiers,
  currentPrice,
  structuralStop,
  ma200,
}: {
  ticker: string;
  playbooks: HorizonPlaybooksBundle | null | undefined;
  intent?: PositionIntent | null;
  onIntentChange?: (intent: PositionIntent | null) => void;
  /** Falls back to this persona's default horizon when no trade/invest intent is set. */
  decisionMode?: DecisionMode;
  /** Long-term tier ladder — rendered inside the "Thesis & tiers" tab (single source, see LongTermTierLadder). */
  entryTiers?: NonNullable<HorizonSignalPayload["entry_tiers"]> | null;
  currentPrice?: number | null;
  structuralStop?: number | null;
  ma200?: number | null;
}) {
  const [intentLocal, setIntentLocal] = useState<PositionIntent | null>(null);
  const [activeHorizon, setActiveHorizon] = useState<HorizonKey>("short");
  const intent = intentProp !== undefined ? intentProp : intentLocal;

  useEffect(() => {
    if (intentProp === undefined) {
      setIntentLocal(getPositionIntent(ticker));
    }
  }, [ticker, intentProp]);

  const handleIntent = (next: PositionIntent | null) => {
    if (intentProp === undefined) {
      setIntentLocal(next);
    }
    onIntentChange?.(next);
  };

  const intentHorizon = useMemo(
    () => (intent ? primaryHorizonFromIntent(intent) : primaryHorizonFromMode(decisionMode ?? "scout")),
    [intent, decisionMode],
  );

  useEffect(() => {
    setActiveHorizon(intentHorizon);
  }, [intentHorizon, ticker]);

  if (!playbooks) return null;

  const available = (["short", "medium", "long"] as const).filter((h) => pickPlaybook(playbooks, h));
  if (available.length === 0) return null;

  const primary = pickPlaybook(playbooks, activeHorizon) ?? pickPlaybook(playbooks, available[0]);
  const sharedLines = useMemo(() => sharedPlaybookContext(playbooks), [playbooks]);

  return (
    <div className="border-b border-td-line/80">
      <div className="px-4 sm:px-6 py-2 flex flex-wrap items-center justify-between gap-2 bg-td-surface/60 border-b border-td-line/80">
        <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-td-muted">Horizon playbooks</p>
        <div className="flex items-center gap-2 flex-wrap">
          <PositionIntentChip ticker={ticker} compact intent={intent} onChange={handleIntent} />
          <span className="text-[10px] text-td-muted hidden sm:inline">
            {intent === "trade" && "Scout mode — swing / tactical primary"}
            {intent === "invest" && "Planner mode — thesis / accumulate primary"}
            {!intent && "Set intent: Scout (trade) vs Planner (invest)"}
          </span>
        </div>
      </div>

      {available.length > 1 && (
        <div className="flex border-b border-td-line/80 px-2 sm:px-4 gap-1 overflow-x-auto">
          {available.map((h) => (
            <button
              key={h}
              type="button"
              onClick={() => setActiveHorizon(h)}
              className={clsx(
                "shrink-0 px-3 py-2 text-xs font-semibold uppercase tracking-wide border-b-2 transition-colors",
                activeHorizon === h
                  ? h === "short"
                    ? "border-td-accent text-td-accent"
                    : h === "medium"
                      ? "border-td-accent text-td-accent"
                      : "border-td-owner text-td-owner"
                  : "border-transparent text-td-muted hover:text-td-text",
                h === intentHorizon && activeHorizon !== h && "ring-1 ring-inset ring-td-line rounded-t"
              )}
            >
              {TAB_META[h].label}
              {h === intentHorizon && (
                <span className="ml-1 text-[9px] opacity-70">★</span>
              )}
            </button>
          ))}
        </div>
      )}

      {primary && (
        <p
          className={clsx(
            "mx-4 sm:mx-6 mt-2 text-[10px] font-medium uppercase tracking-wide",
            activeHorizon === "short"
              ? "text-td-accent/80"
              : activeHorizon === "medium"
                ? "text-td-accent/80"
                : "text-td-owner/80"
          )}
        >
          Viewing: {horizonLabel(activeHorizon)} · {TAB_META[activeHorizon].anchor}
        </p>
      )}

      {sharedLines.length > 0 && (
        <ul className="mx-4 sm:mx-6 mt-3 mb-1 space-y-1 text-sm text-td-muted border-l-2 border-td-line pl-3">
          {sharedLines.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      )}

      {primary && (
        <HorizonPlaybookCard
          data={primary}
          omitNarrativeLines={sharedLines}
          entryTiers={entryTiers}
          currentPrice={currentPrice}
          structuralStop={structuralStop}
          ma200={ma200}
        />
      )}
    </div>
  );
}
