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
import { apiUrl } from "@/lib/apiBase";

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
  setupQuality,
  scoreNote,
  scoreStale,
  regime,
  actionTitle,
  gatesPassed,
  gatesTotal = 4,
  confidencePct,
  confidenceTarget = 55,
  earningsLabel,
}: {
  ticker: string;
  price?: number | null;
  dailyMovePct?: number | null;
  /** Confidence-adjusted headline (act-today). Prefer over raw setup. */
  score?: number | null;
  /** Raw setup quality 0–100 when different from headline */
  setupQuality?: number | null;
  scoreNote?: string | null;
  scoreStale?: boolean;
  regime?: string | null;
  actionTitle?: string | null;
  gatesPassed?: number | null;
  gatesTotal?: number;
  /** Fused confidence — shown as meta, not in 4/4 buy-gate bar */
  confidencePct?: number | null;
  confidenceTarget?: number;
  earningsLabel?: string | null;
}) {
  const move = formatDailyMovePct(dailyMovePct);
  const showSetup =
    setupQuality != null &&
    score != null &&
    Math.abs(Number(setupQuality) - Number(score)) >= 3;
  const confFail =
    confidencePct != null && Number(confidencePct) < Number(confidenceTarget);

  return (
    <div className="sticky top-0 z-[20] border-b border-td-line/80 bg-td-bg/95 backdrop-blur-md px-3 sm:px-5 py-2.5">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <div className="min-w-0">
          <p className="font-mono font-bold text-lg text-td-text">{ticker}</p>
          <div className="flex items-baseline gap-2 flex-wrap">
            {price != null && (
              <span className="text-xl font-bold tabular-nums text-td-accent">${price.toFixed(2)}</span>
            )}
            <span className={clsx("text-sm font-semibold tabular-nums", move.className)}>{move.text}</span>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs">
          {scoreStale ? (
            <span
              className="px-2 py-0.5 rounded border border-td-warn/45 bg-td-warn-weak/40 text-td-warn"
              title={scoreNote || "Price data may be delayed — score suppressed"}
            >
              Score <span className="font-semibold">STALE</span>
            </span>
          ) : score != null ? (
            <span
              className={clsx(
                "px-2 py-0.5 rounded border tabular-nums",
                Number(score) >= 55
                  ? "border-td-accent/40 bg-td-accent-weak/30"
                  : Number(score) >= 30
                    ? "border-td-warn/40 bg-td-warn-weak/30"
                    : "border-td-line bg-td-surface2/80",
              )}
              title={scoreNote || "Confidence-adjusted — gates × fused confidence applied to setup quality"}
            >
              Score{" "}
              <span
                className={clsx(
                  "font-semibold",
                  Number(score) >= 55 ? "text-td-accent" : Number(score) >= 30 ? "text-td-warn" : "text-td-text",
                )}
              >
                {Math.round(Number(score))}
              </span>
              {showSetup && (
                <span className="text-td-muted font-normal ml-1">
                  (setup {Math.round(Number(setupQuality))})
                </span>
              )}
            </span>
          ) : null}
          {regime && (
            <span
              className={clsx(
                "px-2 py-0.5 rounded border font-bold uppercase text-[10px]",
                regime === "UP" && "border-td-accent/40 text-td-accent bg-td-accent-weak/30",
                regime === "EXTENDED" && "border-td-warn/40 text-td-warn bg-td-warn-weak/30",
                regime === "DOWN" && "border-td-crit/40 text-td-crit bg-td-crit-weak/30",
                regime === "NEUTRAL" && "border-td-line text-td-muted"
              )}
            >
              {regime}
            </span>
          )}
          {actionTitle && (
            <span className="text-td-text font-medium truncate max-w-[12rem]" title={actionTitle}>
              {actionTitle}
            </span>
          )}
        </div>
        {(gatesPassed != null || confidencePct != null) && (
          <div className="w-full sm:w-36 shrink-0 space-y-1">
            {gatesPassed != null && (
              <GateProgressBar passed={gatesPassed} total={gatesTotal} variant="buy" />
            )}
            {confidencePct != null && (
              <p
                className={clsx(
                  "text-[10px] leading-tight",
                  confFail ? "text-td-warn/90" : "text-td-muted",
                )}
                title="Sizing / meta-confidence — not counted in the 4-of-4 buy-gate bar"
              >
                Meta-confidence {Math.round(Number(confidencePct))}%
                {confFail ? ` (needs ${Math.round(Number(confidenceTarget))}%)` : ""}
              </p>
            )}
          </div>
        )}
        {earningsLabel && (
          <span className="text-[10px] text-td-warn/90 border border-td-warn/30 rounded px-1.5 py-0.5">
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
      <SignalLevelsPanel signal={signal} />
    </aside>
  );
}

/**
 * Compact ST/MT/LT levels — moved here from flat "Buy/Sell/Support" and "Horizons ST/MT/LT"
 * table columns (removed: both were dense text blobs, and Buy/Sell/Support's own tooltip said
 * to prefer the band columns instead). One place, one row per horizon, consistent with the
 * ticker-detail hero's level rows rather than a separate visual language.
 */
function SignalLevelsPanel({ signal: r }: { signal: Signal }) {
  const rows: { tag: string; text: string; sub?: string }[] = [];
  if (r.st_band) {
    rows.push({
      tag: "ST",
      text: `$${r.st_band.low.toFixed(2)} – $${r.st_band.high.toFixed(2)}`,
      sub: r.short_suggestion ?? undefined,
    });
  }
  if (r.mt_band) {
    rows.push({
      tag: "MT",
      text: `$${r.mt_band.low.toFixed(2)} – $${r.mt_band.high.toFixed(2)}`,
      sub: r.medium_suggestion ?? undefined,
    });
  }
  if (r.lt_band) {
    rows.push({
      tag: "LT",
      text: `$${r.lt_band.low.toFixed(2)} – $${r.lt_band.high.toFixed(2)}${r.lt_band_low_confidence ? " (low conf)" : ""}`,
      sub: r.long_suggestion ?? undefined,
    });
  }
  if (rows.length === 0) return null;
  return (
    <div className="px-4 pb-4 space-y-1.5">
      <p className="text-[10px] font-mono uppercase tracking-wider text-slate-600">Levels</p>
      {rows.map((row) => (
        <div
          key={row.tag}
          className="grid grid-cols-[2.4rem_1fr] items-baseline gap-2 px-2.5 py-1.5 rounded-lg bg-slate-800/60 border border-slate-700/60"
        >
          <span className="text-[10px] font-mono font-bold uppercase tracking-wide text-slate-500">{row.tag}</span>
          <div className="min-w-0">
            <span className="text-[12.5px] font-mono font-semibold text-white tabular-nums">{row.text}</span>
            {row.sub && <p className="text-[10px] text-slate-500 truncate">{row.sub}</p>}
          </div>
        </div>
      ))}
    </div>
  );
}

/** U3 — compact news rail for ticker modal. */
export type CatalystNoteCard = {
  name: string;
  event_type?: string;
  direction: "unlocks" | "breaks" | "watch" | string;
  mechanism: string;
  watch?: string;
  horizon?: string;
  source?: string | null;
  age_label?: string | null;
  url?: string | null;
  headline_count?: number;
  draft_note: string;
  wrap?: string | null;
};

const CATALYST_WRAP_TIMEOUT_MS = 25000;

export function NewsSentimentRail({
  ticker,
  mode,
  label,
  score,
  headlineCount,
  headlines,
  catalystNote,
  sentimentCaveat,
  catalystCards,
}: {
  ticker?: string;
  mode?: string;
  label?: string | null;
  score?: number | null;
  headlineCount?: number | null;
  headlines?: Array<{ title?: string; url?: string | null }>;
  catalystNote?: string | null;
  sentimentCaveat?: string | null;
  catalystCards?: CatalystNoteCard[] | null;
}) {
  const [saved, setSaved] = React.useState<Record<string, "idle" | "saving" | "ok" | "err">>({});
  const [wraps, setWraps] = React.useState<Record<string, CatalystNoteCard>>({});
  const [wrapStatus, setWrapStatus] = React.useState<"idle" | "loading" | "ok" | "cached" | "skipped" | "fallback">("idle");
  const cards = (catalystCards ?? []).slice(0, 4);
  const cardsKey = cards.map((c) => c.event_type || c.name).join("|");

  React.useEffect(() => {
    if (!ticker || cards.length === 0) return;
    setWraps({});
    setWrapStatus("loading");
    const ac = new AbortController();
    const timer = window.setTimeout(() => ac.abort(), CATALYST_WRAP_TIMEOUT_MS);
    const q = mode ? `?mode=${encodeURIComponent(mode)}` : "";
    fetch(apiUrl(`/api/ticker/${encodeURIComponent(ticker)}/catalyst-notes${q}`), {
      signal: ac.signal,
      cache: "no-store",
    })
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => {
        if (!j) {
          setWrapStatus("fallback");
          return;
        }
        const st = String(j.wrap_status || "skipped");
        setWrapStatus(st === "ok" || st === "cached" || st === "skipped" || st === "fallback" ? st : "skipped");
        const next: Record<string, CatalystNoteCard> = {};
        for (const c of j.cards || []) {
          if (c?.event_type) next[c.event_type] = c;
        }
        setWraps(next);
      })
      .catch(() => setWrapStatus("fallback"))
      .finally(() => window.clearTimeout(timer));
    return () => {
      ac.abort();
      window.clearTimeout(timer);
    };
    // cardsKey stands in for the card cluster; avoid refetching on new array identity
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ticker, mode, cardsKey]);

  if (!headlineCount && !headlines?.length && !catalystNote && !cards.length) return null;
  const sentiment = (label || "").trim()
    ? label
    : score != null
      ? score >= 0.55
        ? "Bullish"
        : score <= 0.45
          ? "Bearish"
          : "Neutral"
      : "Neutral";
  const wrapping = wrapStatus === "ok" || wrapStatus === "cached";

  async function addNote(card: CatalystNoteCard) {
    if (!ticker) return;
    const key = card.event_type || card.name;
    const merged = (card.event_type && wraps[card.event_type]) || card;
    setSaved((s) => ({ ...s, [key]: "saving" }));
    try {
      const r = await fetch(apiUrl("/api/behavior/journal"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ticker, action: "note", note: merged.draft_note }),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      setSaved((s) => ({ ...s, [key]: "ok" }));
    } catch {
      setSaved((s) => ({ ...s, [key]: "err" }));
    }
  }

  return (
    <div className="rounded-lg border border-td-info/25 bg-td-info/10/15 p-3 space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[10px] uppercase tracking-wider text-td-info/90 font-semibold">News</span>
        <span className="text-[10px] font-bold uppercase px-1.5 py-0.5 rounded border border-td-info/30 text-td-info">
          {sentiment}
        </span>
        {headlineCount != null && headlineCount > 0 && (
          <span className="text-[10px] text-td-muted">{headlineCount} headlines</span>
        )}
      </div>
      {sentimentCaveat && (
        <p className="text-[11px] text-td-warn/90 leading-snug">{sentimentCaveat}</p>
      )}
      {catalystNote && (
        <p className="text-[11px] text-td-warn/90 leading-snug">{catalystNote}</p>
      )}
      {cards.length > 0 && (
        <div className="space-y-2">
          <p className="text-[10px] text-td-muted">
            Catalyst cards — advisory only; does not change bands or gates.
            {wrapStatus === "loading" ? " Summarizing…" : wrapping ? " Guarded wrap." : ""}
          </p>
          {cards.map((c) => {
            const key = c.event_type || c.name;
            const st = saved[key] || "idle";
            const merged = (c.event_type && wraps[c.event_type]) || c;
            const wrapText = merged.wrap || null;
            const watch = merged.watch || c.watch;
            const tone =
              c.direction === "unlocks"
                ? "border-td-accent/30 text-td-accent"
                : c.direction === "breaks"
                  ? "border-td-crit/30 text-td-crit"
                  : "border-td-line/30 text-td-text";
            return (
              <div key={key} className="rounded-md border border-td-line/70 bg-td-bg/40 p-2 space-y-1">
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className={clsx("text-[9px] font-bold uppercase px-1.5 py-0.5 rounded border", tone)}>
                    {c.direction}
                  </span>
                  <span className="text-[10px] font-semibold text-td-text">{c.name}</span>
                  {c.age_label && <span className="text-[10px] text-td-muted">{c.age_label}</span>}
                  {c.source && <span className="text-[10px] text-td-muted truncate">{c.source}</span>}
                </div>
                {wrapText && (
                  <p className="text-[11px] text-td-text leading-snug">{wrapText}</p>
                )}
                {c.url ? (
                  <a href={c.url} target="_blank" rel="noopener noreferrer" className="text-[11px] text-td-muted leading-snug hover:text-td-info line-clamp-2">
                    {c.mechanism}
                  </a>
                ) : (
                  <p className="text-[11px] text-td-muted leading-snug line-clamp-2">{c.mechanism}</p>
                )}
                {watch && (
                  <p className="text-[10px] text-td-muted">Watch: {watch}{c.horizon ? ` · ${c.horizon}` : ""}</p>
                )}
                {ticker && (
                  <button
                    type="button"
                    onClick={() => addNote(c)}
                    disabled={st === "saving" || st === "ok"}
                    className="text-[10px] font-semibold text-td-info hover:text-td-info disabled:text-td-muted"
                  >
                    {st === "ok" ? "Saved to notes" : st === "saving" ? "Saving…" : st === "err" ? "Retry add to note" : "Add to note"}
                  </button>
                )}
              </div>
            );
          })}
        </div>
      )}
      <ul className="space-y-1.5 max-h-64 overflow-y-auto pr-1">
        {(headlines ?? []).slice(0, 8).map((h, i) => (
          <li key={i} className="text-[11px] text-td-muted leading-snug line-clamp-2">
            {h.url ? (
              <a href={h.url} target="_blank" rel="noopener noreferrer" className="hover:text-td-info" title="Open full article">
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
