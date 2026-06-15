"use client";

import React from "react";
import { clsx } from "clsx";
import type { Signal } from "@/app/page";
import {
  CompactSignalActionStrip,
  TradingGateMiniPills,
  deriveListActionStatus,
  type SignalListContext,
} from "./retailActionUX";
import { gatesForSignal } from "@/lib/signalsTableViewGates";
import { MiniPriceSparkline } from "./MiniPriceSparkline";

/** U1 — compact SVG sparkline from EOD closes (mobile + desktop). */
export { MiniPriceSparkline };

/** U1 — gate pass progress (buy 4/4 or trim 2/4). */
export function GateProgressBar({
  passed,
  total = 4,
  variant = "buy",
  className,
}: {
  passed: number;
  total?: number;
  variant?: "buy" | "trim";
  className?: string;
}) {
  const pct = total > 0 ? Math.min(100, Math.round((passed / total) * 100)) : 0;
  const cleared = passed >= total;
  const minPass = variant === "trim" ? 2 : total;
  const ok = passed >= minPass;
  return (
    <div className={clsx("space-y-0.5", className)} title={`${passed}/${total} gates pass`}>
      <div className="flex items-center justify-between gap-2 text-[9px] uppercase tracking-wider text-slate-500">
        <span>{variant === "trim" ? "Trim gates" : "Buy gates"}</span>
        <span className={clsx("font-bold tabular-nums", ok ? "text-emerald-400" : "text-amber-400")}>
          {passed}/{total}
        </span>
      </div>
      <div className="h-1.5 rounded-full bg-slate-700/80 overflow-hidden flex gap-px">
        {Array.from({ length: total }).map((_, i) => (
          <div
            key={i}
            className={clsx(
              "flex-1 rounded-sm transition-colors",
              i < passed
                ? cleared
                  ? "bg-emerald-500"
                  : ok
                    ? "bg-emerald-500/70"
                    : "bg-amber-500/80"
                : "bg-slate-600/50"
            )}
          />
        ))}
      </div>
    </div>
  );
}

export function formatDailyMovePct(pct: number | null | undefined): { text: string; className: string } {
  if (pct == null || Number.isNaN(pct)) return { text: "—", className: "text-slate-500" };
  const sign = pct >= 0 ? "+" : "";
  return {
    text: `${sign}${pct.toFixed(2)}%`,
    className: pct >= 0 ? "text-emerald-400" : "text-red-400",
  };
}

/** U1 — sticky quote strip for ticker modal (desktop + mobile scroll). */
export function StickyTickerQuoteBar({
  ticker,
  price,
  dailyMovePct,
  score,
  regime,
  actionTitle,
  gatesPassed,
  gatesTotal = 4,
  earningsLabel,
}: {
  ticker: string;
  price?: number | null;
  dailyMovePct?: number | null;
  score?: number | null;
  regime?: string | null;
  actionTitle?: string | null;
  gatesPassed?: number | null;
  gatesTotal?: number;
  earningsLabel?: string | null;
}) {
  const move = formatDailyMovePct(dailyMovePct);
  return (
    <div className="sticky top-0 z-[20] border-b border-slate-700/80 bg-slate-950/95 backdrop-blur-md px-3 sm:px-5 py-2.5">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <div className="min-w-0">
          <p className="font-mono font-bold text-lg text-white">{ticker}</p>
          <div className="flex items-baseline gap-2 flex-wrap">
            {price != null && (
              <span className="text-xl font-bold tabular-nums text-emerald-300">${price.toFixed(2)}</span>
            )}
            <span className={clsx("text-sm font-semibold tabular-nums", move.className)}>{move.text}</span>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs">
          {score != null && (
            <span className="px-2 py-0.5 rounded border border-slate-600 bg-slate-800/80 tabular-nums">
              Score <span className="text-emerald-300 font-semibold">{Math.round(score)}</span>
            </span>
          )}
          {regime && (
            <span
              className={clsx(
                "px-2 py-0.5 rounded border font-bold uppercase text-[10px]",
                regime === "UP" && "border-emerald-500/40 text-emerald-300 bg-emerald-950/30",
                regime === "DOWN" && "border-red-500/40 text-red-300 bg-red-950/30",
                regime === "NEUTRAL" && "border-slate-600 text-slate-400"
              )}
            >
              {regime}
            </span>
          )}
          {actionTitle && (
            <span className="text-slate-300 font-medium truncate max-w-[12rem]" title={actionTitle}>
              {actionTitle}
            </span>
          )}
        </div>
        {gatesPassed != null && (
          <div className="w-full sm:w-32 shrink-0">
            <GateProgressBar passed={gatesPassed} total={gatesTotal} variant="buy" />
          </div>
        )}
        {earningsLabel && (
          <span className="text-[10px] text-amber-300/90 border border-amber-500/30 rounded px-1.5 py-0.5">
            {earningsLabel}
          </span>
        )}
      </div>
    </div>
  );
}

/** U2 — signals workstation detail rail (desktop lg+). */
export function SignalDetailRail({
  signal,
  gateContext,
  tickerActions,
  onOpenDetail,
  onSelectTicker,
}: {
  signal: Signal | null;
  gateContext: SignalListContext;
  tickerActions?: Record<string, { action: string; one_liner: string }>;
  onOpenDetail?: (ticker: string) => void;
  onSelectTicker?: (ticker: string) => void;
}) {
  if (!signal) {
    return (
      <div className="hidden lg:flex flex-col items-center justify-center min-h-[280px] text-slate-500 text-sm border-l border-slate-700/60 bg-slate-900/40 p-6 sticky top-20 self-start w-full">
        Select a ticker from the list
      </div>
    );
  }

  const gates = gatesForSignal(signal, gateContext);
  const listStatus = deriveListActionStatus(signal);
  const move = formatDailyMovePct(signal.daily_move_pct);

  return (
    <aside className="hidden lg:flex flex-col border-l border-slate-700/60 bg-slate-900/50 sticky top-20 self-start max-h-[calc(100vh-5.5rem)] overflow-y-auto w-full">
      <div className="p-4 space-y-4 sticky top-0 bg-slate-900/95 backdrop-blur border-b border-slate-700/50 z-10">
        <div className="flex items-start justify-between gap-2">
          <div>
            <button
              type="button"
              onClick={() => onSelectTicker?.(signal.ticker)}
              className="font-mono text-lg font-bold text-emerald-400 hover:underline"
            >
              {signal.ticker}
            </button>
            <div className="flex items-baseline gap-2 mt-0.5">
              {signal.close != null && (
                <span className="text-white font-semibold tabular-nums">${signal.close.toFixed(2)}</span>
              )}
              <span className={clsx("text-sm font-medium tabular-nums", move.className)}>{move.text}</span>
            </div>
          </div>
          {signal.sparkline_closes && signal.sparkline_closes.length >= 3 && (
            <MiniPriceSparkline closes={signal.sparkline_closes} width={88} height={32} />
          )}
        </div>
        <p className="text-sm font-semibold text-slate-100">{listStatus.title}</p>
        {gates && gates.length > 0 && (
          <>
            <GateProgressBar
              passed={gates.filter((g) => g.pass).length}
              total={4}
              variant="buy"
            />
            <TradingGateMiniPills gates={gates} />
          </>
        )}
        <button
          type="button"
          onClick={() => onOpenDetail?.(signal.ticker)}
          className="w-full text-sm py-2 rounded-lg bg-emerald-600/80 hover:bg-emerald-500 text-white font-medium"
        >
          Open full detail
        </button>
      </div>
      <div className="p-4">
        <CompactSignalActionStrip
          signal={signal}
          listContext={gateContext}
          oneLiner={tickerActions?.[signal.ticker]?.one_liner}
          variant="card"
          onOpenDetail={() => onOpenDetail?.(signal.ticker)}
        />
      </div>
    </aside>
  );
}

/** U3 — compact news rail for ticker modal. */
export function NewsSentimentRail({
  label,
  score,
  headlineCount,
  headlines,
  catalystNote,
}: {
  label?: string | null;
  score?: number | null;
  headlineCount?: number | null;
  headlines?: Array<{ title?: string; url?: string }>;
  catalystNote?: string | null;
}) {
  if (!headlineCount && !headlines?.length && !catalystNote) return null;
  const sentiment =
    score != null
      ? score >= 0.55
        ? "Bullish"
        : score <= 0.45
          ? "Bearish"
          : "Neutral"
      : label ?? "Neutral";

  return (
    <div className="rounded-lg border border-sky-500/25 bg-sky-950/15 p-3 space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[10px] uppercase tracking-wider text-sky-400/90 font-semibold">News</span>
        <span className="text-[10px] font-bold uppercase px-1.5 py-0.5 rounded border border-sky-500/30 text-sky-200">
          {sentiment}
        </span>
        {headlineCount != null && headlineCount > 0 && (
          <span className="text-[10px] text-slate-500">{headlineCount} headlines</span>
        )}
      </div>
      {catalystNote && (
        <p className="text-[11px] text-amber-200/90 leading-snug">{catalystNote}</p>
      )}
      <ul className="space-y-1">
        {(headlines ?? []).slice(0, 3).map((h, i) => (
          <li key={i} className="text-[11px] text-slate-400 leading-snug truncate">
            {h.url ? (
              <a href={h.url} target="_blank" rel="noopener noreferrer" className="hover:text-sky-300">
                {h.title}
              </a>
            ) : (
              h.title
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

/** U4 — trust metrics on Overview (forward tracking + validation). */
export function TrustMetricsStrip({
  forwardHitRate,
  forwardObservations,
  gateCohortEdge,
  paperWinRate,
  className,
}: {
  forwardHitRate?: number | null;
  forwardObservations?: number | null;
  gateCohortEdge?: string | null;
  paperWinRate?: number | null;
  className?: string;
}) {
  const items: { label: string; value: string; sub?: string; tone: "good" | "neutral" | "warn" }[] = [];
  if (forwardHitRate != null) {
    items.push({
      label: "HOLD/ADD 20d",
      value: `${forwardHitRate.toFixed(0)}%`,
      sub: forwardObservations ? `${forwardObservations} obs` : undefined,
      tone: forwardHitRate >= 55 ? "good" : forwardHitRate >= 50 ? "neutral" : "warn",
    });
  }
  if (paperWinRate != null) {
    items.push({
      label: "Paper win",
      value: `${paperWinRate.toFixed(0)}%`,
      tone: paperWinRate >= 55 ? "good" : "neutral",
    });
  }
  if (gateCohortEdge) {
    items.push({ label: "4/4 gates", value: gateCohortEdge, tone: "neutral" });
  }
  if (!items.length) return null;

  return (
    <div
      className={clsx(
        "flex flex-wrap gap-2 rounded-lg border border-emerald-500/20 bg-emerald-950/10 px-3 py-2",
        className
      )}
    >
      <span className="text-[10px] uppercase tracking-wider text-emerald-400/80 font-semibold w-full sm:w-auto sm:mr-1">
        Track record
      </span>
      {items.map((it) => (
        <div
          key={it.label}
          className={clsx(
            "rounded-md border px-2.5 py-1.5 min-w-[5.5rem]",
            it.tone === "good"
              ? "border-emerald-500/30 bg-emerald-950/20"
              : it.tone === "warn"
                ? "border-amber-500/30 bg-amber-950/15"
                : "border-slate-600/50 bg-slate-800/40"
          )}
        >
          <p className="text-[9px] uppercase text-slate-500">{it.label}</p>
          <p className="text-sm font-bold tabular-nums text-slate-100">{it.value}</p>
          {it.sub && <p className="text-[9px] text-slate-500">{it.sub}</p>}
        </div>
      ))}
    </div>
  );
}

/** U4 — mini equity curve from paper MTM history. */
export function MiniEquityCurve({
  points,
  className,
}: {
  points: Array<{ date?: string; value?: number; cumulative_return_pct?: number }>;
  className?: string;
}) {
  if (!points || points.length < 2) return null;
  const vals = points.map((p) => p.cumulative_return_pct ?? p.value ?? 0);
  const min = Math.min(...vals);
  const max = Math.max(...vals);
  const range = max - min || 1;
  const w = 200;
  const h = 48;
  const coords = vals
    .map((v, i) => {
      const x = (i / (vals.length - 1)) * w;
      const y = h - ((v - min) / range) * (h - 4) - 2;
      return `${x},${y}`;
    })
    .join(" ");
  const last = vals[vals.length - 1];
  const positive = last >= (vals[0] ?? 0);

  return (
    <div className={clsx("rounded-lg border border-slate-700/60 bg-slate-900/50 p-3", className)}>
      <div className="flex items-center justify-between gap-2 mb-2">
        <span className="text-[10px] uppercase tracking-wider text-slate-500">Paper equity curve</span>
        <span className={clsx("text-sm font-bold tabular-nums", positive ? "text-emerald-400" : "text-red-400")}>
          {last >= 0 ? "+" : ""}
          {last.toFixed(1)}%
        </span>
      </div>
      <svg viewBox={`0 0 ${w} ${h}`} className="w-full h-12" preserveAspectRatio="none" aria-hidden>
        <polyline
          fill="none"
          stroke={positive ? "rgb(52,211,153)" : "rgb(248,113,113)"}
          strokeWidth="2"
          points={coords}
        />
      </svg>
    </div>
  );
}

export function SignalSparklineCell({ signal }: { signal: Signal }) {
  const move = formatDailyMovePct(signal.daily_move_pct);
  if (!signal.sparkline_closes?.length && signal.close == null) return <span className="text-slate-600">—</span>;
  return (
    <div className="flex flex-col items-end gap-0.5">
      {signal.sparkline_closes && signal.sparkline_closes.length >= 3 && (
        <MiniPriceSparkline closes={signal.sparkline_closes} width={72} height={24} />
      )}
      <span className={clsx("text-[10px] font-semibold tabular-nums", move.className)}>{move.text}</span>
    </div>
  );
}
