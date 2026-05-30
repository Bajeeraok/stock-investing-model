"use client";

import { clsx } from "clsx";

/** What layer drove an overview alert — not the same as ticker-detail horizon cards. */
export type AlertSourceKind = "story" | "trim" | "earnings" | "after_hours" | "macro";

const SOURCE_META: Record<
  AlertSourceKind,
  { abbr: string; label: string; title: string; className: string }
> = {
  story: {
    abbr: "MT",
    label: "Composite",
    title:
      "Regime flip or score drop vs last run — from composite buy score (trend + momentum), same engine as the medium-term column. Not ST/LT horizon verdicts.",
    className: "border-amber-500/40 bg-amber-500/10 text-amber-200/95",
  },
  trim: {
    abbr: "MT",
    label: "Portfolio",
    title:
      "Holding score below trim threshold or 7-layer plan action (e.g. AVOID). Portfolio doctor uses composite score; open ticker for ST/MT/LT playbooks.",
    className: "border-red-500/40 bg-red-500/10 text-red-200/95",
  },
  earnings: {
    abbr: "ST",
    label: "Event",
    title: "Earnings within caution window — near-term calendar risk.",
    className: "border-violet-500/40 bg-violet-500/10 text-violet-200/95",
  },
  after_hours: {
    abbr: "ST",
    label: "AH",
    title: "After-hours move or post-earnings reaction.",
    className: "border-indigo-500/40 bg-indigo-500/10 text-indigo-200/95",
  },
  macro: {
    abbr: "—",
    label: "Macro",
    title: "Market-wide backdrop, not a single-ticker horizon.",
    className: "border-sky-500/40 bg-sky-500/10 text-sky-200/95",
  },
};

export type StoryProvenance = {
  source?: string | null;
  trigger?: string | null;
  horizon?: string | null;
  horizonFlips?: string[] | null;
};

export type TrimProvenance = {
  source?: string | null;
  primaryDriver?: string | null;
  triggers?: string[] | null;
  horizon?: string | null;
};

function storyChipMeta(p?: StoryProvenance | null): { abbr: string; label: string; title: string; className: string } {
  const base = SOURCE_META.story;
  if (!p?.source && !p?.trigger) return base;
  const src = (p.source || "composite").toLowerCase();
  const trig = (p.trigger || "").replace(/_/g, " ");
  const flips = p.horizonFlips?.length ? ` · ${p.horizonFlips.map((h) => h.toUpperCase()).join("/")} flipped` : "";
  if (src === "horizon") {
    return {
      abbr: "ST/MT/LT",
      label: "Horizon",
      title: `Playbook suggestion changed vs prior run${flips}. Open ticker for full horizon cards.`,
      className: "border-violet-500/40 bg-violet-500/10 text-violet-200/95",
    };
  }
  const abbr = p.horizon === "short" ? "ST" : p.horizon === "long" ? "LT" : "MT";
  return {
    abbr,
    label: trig === "regime flip" ? "Regime" : trig === "score drop" ? "Score" : "Composite",
    title: `${base.title} Trigger: ${trig || "change"}${flips}.`,
    className: base.className,
  };
}

function trimChipMeta(p?: TrimProvenance | null): { abbr: string; label: string; title: string; className: string } {
  const base = SOURCE_META.trim;
  if (!p?.source && !p?.primaryDriver) return base;
  const src = (p.source || "").toLowerCase();
  const trig = (p.triggers || []).join(", ").replace(/_/g, " ");
  if (src.includes("plan") && src.includes("composite")) {
    return {
      abbr: "MT",
      label: "Score+Plan",
      title: `Composite score below threshold and 7-layer plan action (REDUCE/AVOID).${trig ? ` ${trig}` : ""}`,
      className: "border-red-500/40 bg-red-500/10 text-red-200/95",
    };
  }
  if (src === "plan" || (p.primaryDriver || "").includes("plan")) {
    return {
      abbr: "Plan",
      label: "7-layer",
      title: `Trim driven mainly by 7-layer plan action.${trig ? ` ${trig}` : ""}`,
      className: "border-orange-500/40 bg-orange-500/10 text-orange-200/95",
    };
  }
  return {
    abbr: "MT",
    label: "Score",
    title: `Trim driven mainly by composite score vs sell_max.${trig ? ` ${trig}` : ""}`,
    className: base.className,
  };
}

export function AlertHorizonChip({
  kind,
  compact = false,
  className,
  story,
  trim,
}: {
  kind: AlertSourceKind;
  compact?: boolean;
  className?: string;
  story?: StoryProvenance | null;
  trim?: TrimProvenance | null;
}) {
  const m =
    kind === "story" ? storyChipMeta(story) : kind === "trim" ? trimChipMeta(trim) : SOURCE_META[kind];
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1 rounded border px-1.5 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-wide shrink-0",
        m.className,
        className
      )}
      title={m.title}
    >
      <span aria-hidden>{m.abbr}</span>
      {!compact && <span className="font-sans normal-case tracking-normal text-[10px] opacity-90">{m.label}</span>}
    </span>
  );
}

/** Optional ST/MT/LT suggestion snapshot from signals table (context only). */
export function formatHorizonSuggestionsLine(input: {
  short_suggestion?: string | null;
  medium_suggestion?: string | null;
  long_suggestion?: string | null;
}): string | null {
  const abbr = (s: string | null | undefined) => {
    if (!s) return null;
    const u = s.toUpperCase();
    if (u.includes("STRONG BUY") || u.includes("BUY") || u.includes("ADD")) return "add";
    if (u.includes("TRIM") || u.includes("SELL") || u.includes("REDUCE") || u.includes("AVOID")) return "trim";
    if (u.includes("WATCH")) return "watch";
    if (u.includes("WAIT") || u.includes("HOLD")) return "hold";
    return u.slice(0, 6).toLowerCase();
  };
  const st = abbr(input.short_suggestion);
  const mt = abbr(input.medium_suggestion);
  const lt = abbr(input.long_suggestion);
  if (!st && !mt && !lt) return null;
  const parts: string[] = [];
  if (st) parts.push(`ST ${st}`);
  if (mt) parts.push(`MT ${mt}`);
  if (lt) parts.push(`LT ${lt}`);
  return parts.join(" · ");
}
