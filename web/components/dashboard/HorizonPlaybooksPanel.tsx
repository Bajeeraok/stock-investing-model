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

type HorizonKey = "short" | "medium" | "long";

const TAB_META: Record<HorizonKey, { label: string }> = {
  short: { label: "Swing" },
  medium: { label: "Position build" },
  long: { label: "Thesis & tiers" },
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
}: {
  ticker: string;
  playbooks: HorizonPlaybooksBundle | null | undefined;
  intent?: PositionIntent | null;
  onIntentChange?: (intent: PositionIntent | null) => void;
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

  const intentHorizon = useMemo(() => primaryHorizonFromIntent(intent), [intent]);

  useEffect(() => {
    setActiveHorizon(intentHorizon);
  }, [intentHorizon, ticker]);

  if (!playbooks) return null;

  const available = (["short", "medium", "long"] as const).filter((h) => pickPlaybook(playbooks, h));
  if (available.length === 0) return null;

  const primary = pickPlaybook(playbooks, activeHorizon) ?? pickPlaybook(playbooks, available[0]);
  const sharedLines = useMemo(() => sharedPlaybookContext(playbooks), [playbooks]);

  return (
    <div className="border-b border-slate-700/80">
      <div className="px-4 sm:px-6 py-2 flex flex-wrap items-center justify-between gap-2 bg-slate-900/60 border-b border-slate-800/80">
        <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-slate-500">Horizon playbooks</p>
        <div className="flex items-center gap-2 flex-wrap">
          <PositionIntentChip ticker={ticker} compact intent={intent} onChange={handleIntent} />
          <span className="text-[10px] text-slate-600 hidden sm:inline">
            {intent === "trade" && "Scout mode — swing / tactical primary"}
            {intent === "invest" && "Planner mode — thesis / accumulate primary"}
            {!intent && "Set intent: Scout (trade) vs Planner (invest)"}
          </span>
        </div>
      </div>

      {available.length > 1 && (
        <div className="flex border-b border-slate-800/80 px-2 sm:px-4 gap-1 overflow-x-auto">
          {available.map((h) => (
            <button
              key={h}
              type="button"
              onClick={() => setActiveHorizon(h)}
              className={clsx(
                "shrink-0 px-3 py-2 text-xs font-semibold uppercase tracking-wide border-b-2 transition-colors",
                activeHorizon === h
                  ? h === "short"
                    ? "border-emerald-500 text-emerald-300"
                    : h === "medium"
                      ? "border-teal-500 text-teal-300"
                      : "border-violet-500 text-violet-300"
                  : "border-transparent text-slate-500 hover:text-slate-300",
                h === intentHorizon && activeHorizon !== h && "ring-1 ring-inset ring-slate-700 rounded-t"
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

      {sharedLines.length > 0 && (
        <ul className="mx-4 sm:mx-6 mt-3 mb-1 space-y-1 text-sm text-slate-400 border-l-2 border-slate-600 pl-3">
          {sharedLines.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      )}

      {primary && (
        <HorizonPlaybookCard data={primary} omitNarrativeLines={sharedLines} />
      )}
    </div>
  );
}
