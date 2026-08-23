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
  primary_driver?: {
    category?: string;
    plain_english?: string;
    headline?: string;
    source?: string;
  } | null;
  driver_category?: string | null;
  driver_chip?: string | null;
  why?: string[];
  catalysts?: NarrativeCatalyst[];
  scenario_ev_pct?: number | null;
  narrative?: string;
  narrative_status?: "ok" | "cached" | "skipped" | "fallback";
  packet_hash?: string;
  errors?: string[];
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
      .catch(() => {
        /* optional card — quietly stay empty */
      })
      .finally(() => {
        window.clearTimeout(timer);
        setLoading(false);
      });
    return () => {
      ac.abort();
      window.clearTimeout(timer);
    };
  }, [ticker, mode]);

  if (!loading && !data) return null;

  if (data?.status === "blocked") {
    return (
      <ReferenceCard
        icon={Sparkles}
        title="What to do"
        description="Plan levels did not line up for this persona — notes are withheld until the packet is consistent."
        body={
          <p className="text-xs text-slate-400 leading-relaxed">
            Trading notes unavailable in this mode right now. Try Swing or Scout, or refresh after the next signal run.
          </p>
        }
      />
    );
  }

  const scan = data?.retail_scan;
  const notes = (data?.trading_notes || data?.narrative || "").trim();
  const noteParagraphs = notes
    ? notes.split(/\n/).map((p) => p.trim()).filter(Boolean)
    : [];
  const driverChip = (data?.driver_chip || data?.driver_category || "").trim();
  const driverHeadline = (data?.primary_driver?.headline || "").trim();
  // retail_scan already covers action / zone / catalyst / stop — do not repeat
  // the same story again under a "Trading notes" header in this card.
  const showTradingNotes = !scan && noteParagraphs.length > 0;
  const whyLines = data?.why ?? [];
  const hasWhy = whyLines.length > 0;

  return (
    <ReferenceCard
      icon={Sparkles}
      title="What to do"
      description="Verdict first, then the levels that matter. Open Why for gate checks."
      body={
        loading ? (
          <p className="text-xs text-slate-500 italic animate-pulse">Building the 10-second scan…</p>
        ) : scan ? (
          <div className="space-y-2">
            <div className="flex flex-wrap items-start gap-2">
              <p className="text-sm font-semibold text-slate-100 leading-snug flex-1 min-w-0">
                {scan.headline}
              </p>
              {driverChip ? (
                <span
                  className="shrink-0 rounded border border-emerald-800/60 bg-emerald-950/40 px-1.5 py-0.5 text-[10px] font-medium text-emerald-300/90"
                  title={driverHeadline || undefined}
                >
                  {driverChip}
                </span>
              ) : null}
            </div>
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
        ) : showTradingNotes ? (
          <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-[10px] uppercase tracking-wide text-emerald-400/90 font-semibold">
                Trading notes
              </p>
              {driverChip ? (
                <span
                  className="rounded border border-emerald-800/60 bg-emerald-950/40 px-1.5 py-0.5 text-[10px] font-medium text-emerald-300/90"
                  title={driverHeadline || undefined}
                >
                  {driverChip}
                </span>
              ) : null}
            </div>
            {noteParagraphs.map((p, i) => (
              <p key={i} className="text-xs text-slate-200 leading-relaxed">
                {p}
              </p>
            ))}
          </div>
        ) : data?.action ? (
          <p className="text-xs text-slate-300 leading-relaxed">{data.action.text}</p>
        ) : undefined
      }
      toggleLabel={hasWhy ? "Why? →" : undefined}
    >
      {hasWhy ? (
        <div className="space-y-1">
          <p className="text-[10px] uppercase tracking-wide text-slate-500 font-semibold">Model checks</p>
          {whyLines.map((line, i) => (
            <p key={i} className="text-xs text-slate-400 leading-relaxed whitespace-pre-wrap">
              {line}
            </p>
          ))}
        </div>
      ) : null}
    </ReferenceCard>
  );
}
