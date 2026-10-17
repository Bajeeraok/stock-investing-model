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

export type ModelCheckGate = {
  id: string;
  label: string;
  passed: boolean;
  detail?: string;
};

export type ModelCheckTarget = {
  kind: string;
  label: string;
  value: string;
  detail?: string;
};

export type ModelCheckNewsDriver = {
  name: string;
  direction: "unlocks" | "breaks" | string;
  summary: string;
  horizon?: string;
};

/** Gate-linked catalyst card from model_checks.gate_linked_catalysts */
export type GateLinkedCatalyst = {
  role: "drove_signal" | "unlock_context" | "risk" | string;
  related_gates: string[];
  clears_gate: boolean;
  watch: string;
  name: string;
  summary: string;
  direction?: string;
  horizon?: string;
  category?: string;
  origin?: "news" | "technical" | string;
};

export type ModelChecks = {
  unlock_when?: string;
  gates?: ModelCheckGate[];
  execution_targets?: ModelCheckTarget[];
  news_drivers?: ModelCheckNewsDriver[];
  gate_linked_catalysts?: GateLinkedCatalyst[];
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
  model_checks?: ModelChecks | null;
  catalysts?: NarrativeCatalyst[];
  scenario_ev_pct?: number | null;
  narrative?: string;
  narrative_status?: "ok" | "cached" | "skipped" | "fallback";
  /** Plain-English translation of model_checks (gates/execution targets/catalysts) —
   * a second, separately-guarded LLM call from `narrative`. Empty when skipped/fallback. */
  why_explainer?: string | null;
  why_explainer_status?: "ok" | "cached" | "skipped" | "fallback";
  packet_hash?: string;
  errors?: string[];
};

const NARRATIVE_TIMEOUT_MS = 30000;

const GATE_LABELS: Record<string, string> = {
  valuation: "Valuation",
  market_weather: "Regime",
  momentum_chop: "Momentum",
  ml_probability: "ML setup",
  confidence: "Confidence",
};

const ROLE_SECTIONS: {
  role: "drove_signal" | "unlock_context" | "risk";
  label: string;
  className: string;
}[] = [
  {
    role: "drove_signal",
    label: "Drove signal",
    className: "border-td-accent/35 bg-td-accent-weak/20 text-td-accent-ink",
  },
  {
    role: "unlock_context",
    label: "Unlock context",
    className: "border-td-warn/35 bg-td-warn-weak/20 text-td-warn",
  },
  {
    role: "risk",
    label: "Risk",
    className: "border-td-crit/35 bg-td-crit-weak/20 text-td-crit",
  },
];

function gateLabel(id: string): string {
  return GATE_LABELS[id] || id.replace(/_/g, " ");
}

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
          <p className="text-xs text-td-muted leading-relaxed">
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
  const checks = data?.model_checks ?? null;
  const whyLines = data?.why ?? [];
  const linked = checks?.gate_linked_catalysts ?? [];
  const hasStructuredWhy =
    !!checks &&
    !!(
      checks.unlock_when ||
      (checks.gates && checks.gates.length > 0) ||
      (checks.execution_targets && checks.execution_targets.length > 0) ||
      linked.length > 0 ||
      (checks.news_drivers && checks.news_drivers.length > 0)
    );
  const hasWhy = hasStructuredWhy || whyLines.length > 0;

  return (
    <ReferenceCard
      icon={Sparkles}
      title="What to do"
      description="Verdict first, then the levels that matter. Open Why for gate checks."
      body={
        loading ? (
          <p className="text-xs text-td-muted italic animate-pulse">Building the 10-second scan…</p>
        ) : scan ? (
          <div className="space-y-2">
            <div className="flex flex-wrap items-start gap-2">
              <p className="text-sm font-semibold text-td-text leading-snug flex-1 min-w-0">
                {scan.headline}
              </p>
              {driverChip ? (
                <span
                  className="shrink-0 rounded border border-td-accent/40/60 bg-td-accent-weak/40 px-1.5 py-0.5 text-[10px] font-medium text-td-accent/90"
                  title={driverHeadline || undefined}
                >
                  {driverChip}
                </span>
              ) : null}
            </div>
            <p className="text-xs text-td-muted leading-relaxed">{scan.reason}</p>
            <ul className="space-y-1">
              {scan.lines.map((line, i) => (
                <li key={i} className="text-xs text-td-text leading-relaxed">
                  {line}
                </li>
              ))}
            </ul>
            {scan.timing ? (
              <p className="text-[11px] text-td-muted italic">{scan.timing}</p>
            ) : null}
          </div>
        ) : showTradingNotes ? (
          <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-[10px] uppercase tracking-wide text-td-accent/90 font-semibold">
                Trading notes
              </p>
              {driverChip ? (
                <span
                  className="rounded border border-td-accent/40/60 bg-td-accent-weak/40 px-1.5 py-0.5 text-[10px] font-medium text-td-accent/90"
                  title={driverHeadline || undefined}
                >
                  {driverChip}
                </span>
              ) : null}
            </div>
            {noteParagraphs.map((p, i) => (
              <p key={i} className="text-xs text-td-text leading-relaxed">
                {p}
              </p>
            ))}
          </div>
        ) : data?.action ? (
          <p className="text-xs text-td-text leading-relaxed">{data.action.text}</p>
        ) : undefined
      }
      toggleLabel={hasWhy ? "Why? →" : undefined}
    >
      {hasWhy ? (
        hasStructuredWhy && checks ? (
          <ModelChecksPanel checks={checks} whyExplainer={data?.why_explainer} />
        ) : (
          <div className="space-y-1">
            <p className="text-[10px] uppercase tracking-wide text-td-muted font-semibold">Model checks</p>
            {whyLines.map((line, i) => (
              <p key={i} className="text-xs text-td-muted leading-relaxed whitespace-pre-wrap">
                {line}
              </p>
            ))}
          </div>
        )
      ) : null}
    </ReferenceCard>
  );
}

function ModelChecksPanel({
  checks,
  whyExplainer,
}: {
  checks: ModelChecks;
  whyExplainer?: string | null;
}) {
  const unlock = (checks.unlock_when || "").trim();
  const gates = checks.gates ?? [];
  const targets = checks.execution_targets ?? [];
  const linked = (checks.gate_linked_catalysts ?? []).slice(0, 5);
  const newsFallback =
    linked.length === 0 ? (checks.news_drivers ?? []).slice(0, 3) : [];
  const explainer = (whyExplainer || "").trim();

  return (
    <div className="space-y-3">
      <p className="text-[10px] uppercase tracking-wide text-td-muted font-semibold">Model checks</p>

      {/* Plain-English translation of the gates/targets/catalysts below — the numbers and
          pills stay put underneath as the verifiable detail; this is a reading aid on top
          of them, not a replacement. Silently absent when the LLM path is unavailable. */}
      {explainer ? (
        <p className="text-xs text-td-text leading-relaxed rounded-lg border border-td-line/60 bg-td-surface2/40 px-2.5 py-2">
          {explainer}
        </p>
      ) : null}

      {unlock ? (
        <div className="rounded-lg border border-td-warn/35 bg-td-warn-weak/25 px-2.5 py-2">
          <p className="text-xs font-semibold text-td-warn leading-snug">{unlock}</p>
        </div>
      ) : null}

      {gates.length > 0 ? (
        <div className="space-y-1.5">
          <p className="text-[10px] uppercase tracking-wide text-td-muted font-medium">Logic checks</p>
          <div className="flex flex-wrap gap-1.5">
            {gates.map((g) => (
              <span
                key={g.id}
                title={g.detail || undefined}
                className={
                  g.passed
                    ? "inline-flex items-center gap-1 rounded-full border border-td-accent/40 bg-td-accent-weak/30 px-2 py-0.5 text-[10px] font-medium text-td-accent-ink"
                    : "inline-flex items-center gap-1 rounded-full border border-td-crit/35 bg-td-crit-weak/25 px-2 py-0.5 text-[10px] font-medium text-td-crit/90"
                }
              >
                <span aria-hidden>{g.passed ? "✓" : "✗"}</span>
                {g.label}
              </span>
            ))}
          </div>
        </div>
      ) : null}

      {targets.length > 0 ? (
        <div className="space-y-1.5">
          <p className="text-[10px] uppercase tracking-wide text-td-muted font-medium">Execution targets</p>
          <ul className="space-y-1">
            {targets.map((t) => (
              <li
                key={`${t.kind}-${t.value}`}
                className="flex items-baseline justify-between gap-2 text-xs leading-relaxed"
              >
                <span className="text-td-muted shrink-0">{t.label}</span>
                <span className="text-td-text font-medium text-right tabular-nums">{t.value}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {linked.length > 0 ? (
        <div className="space-y-2">
          <p className="text-[10px] uppercase tracking-wide text-td-muted font-medium">
            Gate-linked catalysts
          </p>
          {ROLE_SECTIONS.map(({ role, label, className }) => {
            const rows = linked.filter((c) => c.role === role);
            if (!rows.length) return null;
            return (
              <div key={role} className="space-y-1.5">
                <p className="text-[10px] font-medium text-td-muted">{label}</p>
                <ul className="space-y-1.5">
                  {rows.map((c, i) => (
                    <li
                      key={`${role}-${c.name}-${i}`}
                      className={`rounded-md border px-2 py-1.5 ${className}`}
                    >
                      <div className="flex flex-wrap items-center gap-1.5">
                        <span className="text-xs font-medium leading-snug">{c.summary || c.name}</span>
                        {!c.clears_gate ? (
                          <span className="text-[9px] uppercase tracking-wide opacity-70">
                            context only
                          </span>
                        ) : null}
                      </div>
                      {c.related_gates?.length ? (
                        <p className="mt-0.5 text-[10px] opacity-80">
                          Related: {c.related_gates.map(gateLabel).join(", ")}
                        </p>
                      ) : null}
                      {c.watch ? (
                        <p className="mt-0.5 text-[10px] opacity-90">Watch: {c.watch}</p>
                      ) : null}
                      {c.horizon ? (
                        <p className="text-[10px] opacity-60">{c.horizon}</p>
                      ) : null}
                    </li>
                  ))}
                </ul>
              </div>
            );
          })}
        </div>
      ) : newsFallback.length > 0 ? (
        <div className="space-y-1.5">
          <p className="text-[10px] uppercase tracking-wide text-td-muted font-medium">
            Company / event catalysts
          </p>
          <ul className="space-y-1">
            {newsFallback.map((n, i) => (
              <li key={`${n.name}-${i}`} className="text-xs text-td-text leading-relaxed">
                <span className="text-td-text">{n.summary || n.name}</span>
                {n.horizon ? <span className="text-td-muted"> · {n.horizon}</span> : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
