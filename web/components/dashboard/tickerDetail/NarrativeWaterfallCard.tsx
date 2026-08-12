"use client";

import { useEffect, useState } from "react";
import { Sparkles } from "lucide-react";
import { apiUrl } from "@/lib/apiBase";
import type { DecisionMode } from "@/lib/decisionMode";
import { ReferenceCard, fmtPct } from "./ReferenceDetailGrid";

export type NarrativeAction = {
  action: "WAIT" | "PLACE_LIMIT" | "STARTER_BUY" | "BUY" | "HOLD" | "STAND_ASIDE";
  limit_prices: number[];
  tranche_pct: number;
  stop: number | null;
  invalidation: number | null;
  review_by: string;
  forbidden: string[];
  text: string;
};

export type NarrativeCatalyst = {
  name: string;
  direction: "unlocks" | "breaks";
  mechanism: string;
  watch: string;
  horizon: string;
};

export type NarrativeWaterfall = {
  status: "ok" | "blocked";
  ticker?: string;
  mode?: string;
  asof?: string;
  action?: NarrativeAction;
  why?: string[];
  catalysts?: NarrativeCatalyst[];
  scenario_ev_pct?: number | null;
  narrative?: string;
  narrative_status?: "ok" | "cached" | "skipped" | "fallback";
  packet_hash?: string;
};

const NARRATIVE_TIMEOUT_MS = 30000;

const ACTION_LABEL: Record<NarrativeAction["action"], string> = {
  WAIT: "Wait",
  PLACE_LIMIT: "Place limit",
  STARTER_BUY: "Starter buy",
  BUY: "Buy",
  HOLD: "Hold",
  STAND_ASIDE: "Stand aside",
};

export function NarrativeWaterfallCard({ ticker, mode }: { ticker: string; mode: DecisionMode }) {
  const [data, setData] = useState<NarrativeWaterfall | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!ticker) return;
    setData(null);
    setLoading(true);
    const ac = new AbortController();
    const timer = window.setTimeout(() => ac.abort(), NARRATIVE_TIMEOUT_MS);
    fetch(apiUrl(`/api/ticker/${ticker}/narrative?mode=${mode}`), { signal: ac.signal, cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => {
        if (j) setData(j as NarrativeWaterfall);
      })
      .catch(() => {/* optional card — quietly stay empty */})
      .finally(() => {
        window.clearTimeout(timer);
        setLoading(false);
      });
    return () => {
      ac.abort();
      window.clearTimeout(timer);
    };
  }, [ticker, mode]);

  if (data?.status === "blocked") return null;
  if (!loading && !data) return null;

  const action = data?.action;
  const usingNarrative = Boolean(
    data?.narrative && (data.narrative_status === "ok" || data.narrative_status === "cached"),
  );

  return (
    <ReferenceCard
      icon={Sparkles}
      title="Trade narrative"
      description="Deterministic action contract, explained — plus a guarded narrative that can only cite numbers already in the data."
      stats={
        action
          ? [
              { label: "Action", value: ACTION_LABEL[action.action] },
              { label: "Scenario EV", value: fmtPct(data?.scenario_ev_pct ?? null) },
            ]
          : undefined
      }
      body={
        loading ? (
          <p className="text-xs text-slate-500 italic animate-pulse">Building trade narrative…</p>
        ) : usingNarrative ? (
          <p className="text-xs text-slate-300 leading-relaxed">{data!.narrative}</p>
        ) : action ? (
          <p className="text-xs text-slate-300 leading-relaxed">{action.text}</p>
        ) : undefined
      }
      toggleLabel="Full explanation & catalysts"
    >
      {data?.why && data.why.length > 0 && (
        <div className="space-y-1">
          {data.why.map((line, i) => (
            <p key={i} className="text-xs text-slate-400 leading-relaxed whitespace-pre-wrap">
              {line}
            </p>
          ))}
        </div>
      )}
    </ReferenceCard>
  );
}
