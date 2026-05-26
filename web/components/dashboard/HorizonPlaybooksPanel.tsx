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
  const secondary = available.filter((h) => h !== activeHorizon && pickPlaybook(playbooks, h));

  return (
    <div className="border-b border-slate-700/80">
      <div className="px-4 sm:px-6 py-2 flex flex-wrap items-center justify-between gap-2 bg-slate-900/60 border-b border-slate-800/80">
        <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-slate-500">Horizon playbooks</p>
        <div className="flex items-center gap-2 flex-wrap">
          <PositionIntentChip ticker={ticker} compact intent={intent} onChange={handleIntent} />
          <span className="text-[10px] text-slate-600 hidden sm:inline">
            {intent === "trade" && "Trade → swing primary"}
            {intent === "invest" && "Invest → thesis primary"}
            {!intent && "Set intent to tune primary playbook"}
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

      {primary && <HorizonPlaybookCard data={primary} />}

      {secondary.length > 0 && (
        <div className="border-t border-slate-800/80">
          <p className="px-4 sm:px-6 pt-2 text-[10px] uppercase tracking-wider text-slate-600">Also available</p>
          {secondary.map((h) => {
            const pb = pickPlaybook(playbooks, h);
            return pb ? <HorizonPlaybookCard key={h} data={pb} compact /> : null;
          })}
        </div>
      )}
    </div>
  );
}
