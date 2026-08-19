"use client";

import { useEffect, useState } from "react";
import { Sparkles } from "lucide-react";
import { apiUrl } from "@/lib/apiBase";
import type { DecisionMode } from "@/lib/decisionMode";
import { ReferenceCard } from "./ReferenceDetailGrid";

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

export type RetailScan = {
  headline: string;
  reason: string;
  lines: string[];
  timing: string;
  text: string;
  starter_only_zone?: boolean;
};

export type NarrativeWaterfall = {
  status: "ok" | "blocked";
  ticker?: string;
  mode?: string;
  asof?: string;
  action?: NarrativeAction;
  retail_scan?: RetailScan | null;
  trading_notes?: string | null;
  why?: string[];
  catalysts?: NarrativeCatalyst[];
  scenario_ev_pct?: number | null;
  narrative?: string;
  narrative_status?: "ok" | "cached" | "skipped" | "fallback";
  packet_hash?: string;
};

const NARRATIVE_TIMEOUT_MS = 30000;

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

  const scan = data?.retail_scan;
  const notes = (data?.trading_notes || data?.narrative || "").trim();
  const noteParagraphs = notes
    ? notes.split(/\n\s*\n/).map((p) => p.trim()).filter(Boolean)
    : [];

  return (
    <ReferenceCard
      icon={Sparkles}
      title="What to do"
      description="Verdict first, then the four numbers that matter. Why opens trading notes, then the model checks."
      body={
        loading ? (
          <p className="text-xs text-slate-500 italic animate-pulse">Building the 10-second scan…</p>
        ) : scan ? (
          <div className="space-y-2">
            <p className="text-sm font-semibold text-slate-100 leading-snug">{scan.headline}</p>
            <p className="text-xs text-slate-400 leading-relaxed">{scan.reason}</p>
            <ul className="space-y-1">
              {scan.lines.map((line, i) => (
                <li key={i} className="text-xs text-slate-200 leading-relaxed">
                  {line}
                </li>
              ))}
            </ul>
            {scan.timing ? (
              <p className="text-[11px] text-slate-500 italic">{scan.timing}</p>
            ) : null}
          </div>
        ) : data?.action ? (
          <p className="text-xs text-slate-300 leading-relaxed">{data.action.text}</p>
        ) : undefined
      }
      toggleLabel="Why? →"
    >
      {noteParagraphs.length > 0 && (
        <div className="space-y-2">
          <p className="text-[10px] uppercase tracking-wide text-emerald-400/90 font-semibold">Trading notes</p>
          {noteParagraphs.map((p, i) => (
            <p key={i} className="text-xs text-slate-200 leading-relaxed">
              {p}
            </p>
          ))}
        </div>
      )}
      {data?.why && data.why.length > 0 && (
        <div className={noteParagraphs.length > 0 ? "mt-3 space-y-1 border-t border-slate-800 pt-2" : "space-y-1"}>
          <p className="text-[10px] uppercase tracking-wide text-slate-500 font-semibold">Model checks</p>
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
