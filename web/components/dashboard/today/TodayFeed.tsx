"use client";

/**
 * Today tab — holdings-first feed from the Thrive Alpha redesign:
 *   market-weather teaser (→ Markets) · Since yesterday (upgrades / downgrades / score-only)
 *   · My book · Market map (sector ETFs) · This week (macro + held earnings) · catalyst strip
 *   · one-line portfolio teaser (→ Portfolio, the canonical home for summary/regime).
 */

import { useEffect, useMemo, useState, type ReactNode } from "react";
import { clsx } from "clsx";
import { ChevronRight } from "lucide-react";
import type { EconomicCalendarEvent, PortfolioHolding, WhatChanged } from "@/app/page";
import type { TradingLens } from "@/lib/tradingLens";
import { apiUrl } from "@/lib/apiBase";

export type WeatherTone = "up" | "caution" | "down";

export type MarketWeather = {
  tone: WeatherTone;
  label: string;
  detail: string | null;
};

const WEATHER_STYLE: Record<WeatherTone, { box: string; text: string; dot: string }> = {
  up: { box: "bg-td-accent-weak/70 border-td-accent/30", text: "text-td-accent", dot: "bg-td-accent" },
  caution: { box: "bg-td-warn-weak/70 border-td-warn/35", text: "text-td-warn", dot: "bg-td-warn" },
  down: { box: "bg-td-crit-weak/70 border-td-crit/35", text: "text-td-crit", dot: "bg-td-crit" },
};

/** Up / Caution / Down — one name for the market-regime gate everywhere ("weather"). */
export function deriveMarketWeather(input: {
  regimeBullPct: number | null | undefined;
  macroRegime?: string | null;
  rotationRisk?: string | null;
  primaryMessage?: string | null;
  temperatureLabel?: string | null;
  vix?: number | null;
  forecastHeadline?: string | null;
  /** retail_market_decisions.market_context.quadrant — the backend's reconciled read. */
  quadrant?: string | null;
}): MarketWeather {
  const bull = input.regimeBullPct;
  let tone: WeatherTone = "caution";
  let label = "Caution";
  if (input.quadrant === "best_buy_zone" && (bull == null || bull >= 60)) {
    // Short-term fear inside a strong bull regime — the backend already reconciled this as
    // a dip-buy setup; calling it "Caution" next to "best buy opportunity" contradicted it.
    tone = "up";
    label = "Up — dips are buyable";
  } else if (bull != null && bull >= 60 && input.macroRegime !== "Risk-Off" && input.rotationRisk !== "High") {
    tone = "up";
    label = "Up";
  } else if ((bull != null && bull <= 40) || (input.macroRegime === "Risk-Off" && (bull == null || bull < 60))) {
    tone = "down";
    label = "Down";
  }
  const headline = input.primaryMessage ?? input.forecastHeadline ?? null;
  const bits = [
    headline && headline === headline.toUpperCase() ? headline.charAt(0) + headline.slice(1).toLowerCase() : headline,
    input.temperatureLabel ? `temperature ${input.temperatureLabel.toLowerCase()}` : null,
    input.vix != null ? `VIX ${input.vix.toFixed(1)}` : null,
    input.rotationRisk && input.rotationRisk !== "Low" ? `rotation risk ${input.rotationRisk.toLowerCase()}` : null,
  ].filter(Boolean);
  return { tone, label, detail: bits.length ? bits.join(" · ") : null };
}

function Card({ title, right, children, className }: { title: ReactNode; right?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={clsx("rounded-2xl border border-td-line bg-td-surface px-4 py-3.5", className)}>
      <div className="flex items-baseline justify-between gap-2 mb-2">
        <h3 className="text-[11.5px] font-semibold uppercase tracking-wider text-td-muted">{title}</h3>
        {right}
      </div>
      {children}
    </section>
  );
}

// ── Since yesterday ─────────────────────────────────────────────────────────

type DiffKind = "up" | "down" | "score";
type DiffRow = { ticker: string; kind: DiffKind; reason: string; right: string; held: boolean };

const SUGG_RANK = (s: string): number => {
  const u = s.toUpperCase();
  if (/SELL|TRIM|REDUCE|AVOID|EXIT/.test(u)) return 0;
  if (/ADD|BUY/.test(u)) return 2;
  return 1;
};
const REGIME_RANK: Record<string, number> = { DOWN: 0, NEUTRAL: 1, UP: 2 };
const LENS_HORIZON: Record<TradingLens, string> = { scout: "Short-term", swing: "Medium-term", owner: "Long-term" };

function titleCase(s: string): string {
  return s
    .toLowerCase()
    .replace(/\b\w/g, (c) => c.toUpperCase())
    .replace(/Consider /, "");
}

function classifyChange(w: WhatChanged, lens: TradingLens, held: boolean): DiffRow | null {
  const changes = w.changes ?? [];
  if (!changes.length) return null;
  const suggRe = /^(Short|Medium|Long)-term: (.+?) → (.+)$/;
  const suggs = changes
    .map((c) => c.match(suggRe))
    .filter(Boolean)
    .map((m) => ({ horizon: `${m![1]}-term`, from: m![2], to: m![3] }));
  const pick = suggs.find((s) => s.horizon === LENS_HORIZON[lens]) ?? suggs[0];
  const regimeM = changes.map((c) => c.match(/^Regime (\w+) → (\w+)$/)).find(Boolean);
  const scoreM = (w.summary ?? "").match(/:\s*(\d+|\?)\s*→\s*(\d+|\?)/);

  let kind: DiffKind = "score";
  if (pick) {
    const d = SUGG_RANK(pick.to) - SUGG_RANK(pick.from);
    kind = d > 0 ? "up" : d < 0 ? "down" : "score";
  }
  if (kind === "score" && regimeM) {
    const d = (REGIME_RANK[regimeM[2]] ?? 1) - (REGIME_RANK[regimeM[1]] ?? 1);
    kind = d > 0 ? "up" : d < 0 ? "down" : "score";
  }
  const reason =
    changes.find((c) => !suggRe.test(c) && !/^Score (up|down)/.test(c)) ?? changes.find((c) => !suggRe.test(c)) ?? changes[0];
  const parts: string[] = [];
  if (scoreM && scoreM[1] !== "?" && scoreM[2] !== "?") parts.push(`${scoreM[1]}→${scoreM[2]}`);
  if (pick) parts.push(`${titleCase(pick.from)}→${titleCase(pick.to)}`);
  return { ticker: w.ticker, kind, reason, right: parts.join(" · "), held };
}

export function SinceYesterdayCard({
  items,
  lens,
  heldTickers,
  onTickerClick,
}: {
  items: WhatChanged[];
  lens: TradingLens;
  heldTickers: Set<string>;
  onTickerClick?: (ticker: string) => void;
}) {
  const rows = useMemo(() => {
    const out = items
      .map((w) => classifyChange(w, lens, heldTickers.has(w.ticker.toUpperCase())))
      .filter((r): r is DiffRow => r != null);
    // Holdings first, then real stance changes before score-only noise.
    const kindOrder: Record<DiffKind, number> = { down: 0, up: 1, score: 2 };
    return out.sort((a, b) => Number(b.held) - Number(a.held) || kindOrder[a.kind] - kindOrder[b.kind]);
  }, [items, lens, heldTickers]);
  const counts = { up: 0, down: 0, score: 0 } as Record<DiffKind, number>;
  for (const r of rows) counts[r.kind]++;
  const [filter, setFilter] = useState<DiffKind>(() => (counts.up ? "up" : counts.down ? "down" : "score"));
  const [showAll, setShowAll] = useState(false);
  const shown = rows.filter((r) => r.kind === filter);
  const visible = showAll ? shown : shown.slice(0, 4);

  const CHIPS: { id: DiffKind; label: string; on: string }[] = [
    { id: "up", label: "Upgrades", on: "bg-td-accent-weak text-td-accent" },
    { id: "down", label: "Downgrades", on: "bg-td-crit-weak text-td-crit" },
    { id: "score", label: "Score only", on: "bg-td-surface2 text-td-text" },
  ];

  return (
    <Card title={`Since yesterday · ${rows.length}`}>
      {rows.length === 0 ? (
        <p className="text-[12.5px] text-td-muted">No changes vs the last saved run.</p>
      ) : (
        <>
          <div className="flex gap-1.5 overflow-x-auto pb-1">
            {CHIPS.map((c) => (
              <button
                key={c.id}
                type="button"
                onClick={() => {
                  setFilter(c.id);
                  setShowAll(false);
                }}
                className={clsx(
                  "shrink-0 rounded-full px-3 py-1.5 text-[11.5px] font-semibold transition-colors",
                  filter === c.id ? c.on : "bg-td-surface2/60 text-td-muted hover:text-td-text",
                )}
              >
                {c.label} {counts[c.id]}
              </button>
            ))}
          </div>
          <ul className="mt-1 divide-y divide-td-line">
            {visible.map((r) => (
              <li key={r.ticker}>
                <button
                  type="button"
                  onClick={() => onTickerClick?.(r.ticker)}
                  className="w-full flex items-center justify-between gap-3 py-2.5 text-left hover:bg-td-surface2/40 rounded-md -mx-1 px-1"
                >
                  <span className="min-w-0">
                    <span className="flex items-center gap-1.5">
                      <span className="font-mono text-[13px] font-bold text-td-text">{r.ticker}</span>
                      {r.held && <span className="text-[9.5px] font-mono uppercase text-td-owner">held</span>}
                    </span>
                    <span className="block text-[11.5px] text-td-muted truncate">{r.reason}</span>
                  </span>
                  <span className="font-mono text-[11.5px] text-td-muted whitespace-nowrap">{r.right}</span>
                </button>
              </li>
            ))}
            {shown.length === 0 && <li className="py-2.5 text-[12px] text-td-muted">None in this group.</li>}
          </ul>
          {shown.length > 4 && (
            <button
              type="button"
              onClick={() => setShowAll((v) => !v)}
              className="mt-1 text-[11.5px] font-semibold text-td-accent hover:brightness-110"
            >
              {showAll ? "Show fewer" : `Show all ${shown.length} ›`}
            </button>
          )}
        </>
      )}
    </Card>
  );
}

// ── My book ─────────────────────────────────────────────────────────────────

const BOOK_CHIP_MAX = 8;

export function MyBookCard({
  holdings,
  scoreDelta,
  onTickerClick,
  onOpenPortfolio,
}: {
  holdings: PortfolioHolding[];
  scoreDelta: Map<string, number>;
  onTickerClick?: (ticker: string) => void;
  onOpenPortfolio?: () => void;
}) {
  if (!holdings.length) return null;
  // Same ticker across accounts (e.g. NVDA in two brokerages) → one chip, values summed.
  const merged = new Map<string, PortfolioHolding>();
  for (const h of holdings) {
    const k = h.ticker.toUpperCase();
    const prev = merged.get(k);
    merged.set(k, prev ? { ...prev, value: (prev.value ?? 0) + (h.value ?? 0) } : h);
  }
  const needsAction = (h: PortfolioHolding) => /TRIM|REDUCE|SELL|AVOID|ADD|BUY/i.test(h.action || h.suggestion || "");
  const all = Array.from(merged.values()).sort(
    (a, b) => Number(needsAction(b)) - Number(needsAction(a)) || (b.value ?? 0) - (a.value ?? 0),
  );
  const sorted = all.slice(0, BOOK_CHIP_MAX);
  const hidden = all.length - sorted.length;
  return (
    <Card
      title={`My book · ${merged.size}`}
      right={
        onOpenPortfolio && (
          <button type="button" onClick={onOpenPortfolio} className="text-[11.5px] font-semibold text-td-accent">
            Portfolio ›
          </button>
        )
      }
    >
      <div className="flex flex-wrap gap-2">
        {sorted.map((h) => {
          const d = scoreDelta.get(h.ticker.toUpperCase());
          const act = (h.action || h.suggestion || "Hold").replace(/^CONSIDER\s+/i, "");
          const actLabel = titleCase(act.split(/[\s/]/)[0] || "Hold");
          const trim = /TRIM|REDUCE|SELL|AVOID/i.test(act);
          return (
            <button
              key={h.ticker}
              type="button"
              onClick={() => onTickerClick?.(h.ticker)}
              className="shrink-0 w-[4.75rem] rounded-xl bg-td-surface2 py-2 text-center hover:bg-td-surface2/70"
              title={h.action_today ?? h.suggestion}
            >
              <span className="block font-mono text-[12px] font-bold text-td-text">{h.ticker}</span>
              <span className={clsx("block text-[10.5px] mt-0.5", trim ? "text-td-warn" : "text-td-muted")}>
                {d != null && d !== 0 && (
                  <span className={d > 0 ? "text-td-accent" : "text-td-crit"}>{d > 0 ? "▲ " : "▼ "}</span>
                )}
                {actLabel}
              </span>
            </button>
          );
        })}
        {hidden > 0 && onOpenPortfolio && (
          <button
            type="button"
            onClick={onOpenPortfolio}
            className="shrink-0 w-[4.75rem] rounded-xl border border-dashed border-td-line py-2 text-center text-[11px] font-semibold text-td-muted hover:text-td-text"
          >
            +{hidden} more
          </button>
        )}
      </div>
    </Card>
  );
}

// ── Market map ──────────────────────────────────────────────────────────────

type SectorMapPayload = {
  spy?: { ticker: string; change_pct: number | null } | null;
  sectors?: Array<{ ticker: string; name: string; change_pct: number | null }>;
  error?: string;
};

function heatBg(pct: number | null): string {
  if (pct == null) return "rgb(var(--td-surface2))";
  const a = Math.min(1, Math.abs(pct) / 1.5);
  const base = pct >= 0 ? "var(--td-accent)" : "var(--td-crit)";
  return `rgb(${base} / ${(0.08 + a * 0.32).toFixed(2)})`;
}

export function MarketMapCard() {
  const [data, setData] = useState<SectorMapPayload | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    const ac = new AbortController();
    fetch(apiUrl("/api/sector-map"), { signal: ac.signal, cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => (j ? setData(j as SectorMapPayload) : setFailed(true)))
      .catch(() => setFailed(true));
    return () => ac.abort();
  }, []);
  const spy = data?.spy?.change_pct;
  const sectors = (data?.sectors ?? []).filter((s) => s.change_pct != null);
  return (
    <Card
      title="Market map"
      right={
        spy != null && (
          <span className={clsx("font-mono text-[12px] font-semibold", spy >= 0 ? "text-td-accent" : "text-td-crit")}>
            SPY {spy >= 0 ? "+" : ""}
            {spy.toFixed(2)}%
          </span>
        )
      }
    >
      {sectors.length ? (
        <div className="grid grid-cols-4 gap-1.5">
          {sectors.map((s) => (
            <div key={s.ticker} className="rounded-lg px-2 py-1.5 font-mono" style={{ background: heatBg(s.change_pct) }} title={s.name}>
              <span className="block text-[11px] font-bold text-td-text">{s.ticker}</span>
              <span className="block text-[10.5px] text-td-text/85">
                {(s.change_pct ?? 0) >= 0 ? "+" : ""}
                {(s.change_pct ?? 0).toFixed(1)}%
              </span>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-[12px] text-td-muted">{failed || data?.error ? "Sector data unavailable right now." : "Loading sectors…"}</p>
      )}
    </Card>
  );
}

// ── This week ───────────────────────────────────────────────────────────────

function eventDate(e: EconomicCalendarEvent): Date | null {
  const raw = e.date ?? (e["datetime"] as string | undefined) ?? (e["time"] as string | undefined);
  if (!raw) return null;
  const d = new Date(String(raw).length <= 10 ? `${raw}T12:00:00` : String(raw));
  return Number.isNaN(d.getTime()) ? null : d;
}

export function ThisWeekCard({
  events,
  heldEarnings,
  onOpenCalendar,
}: {
  events: EconomicCalendarEvent[];
  heldEarnings: Array<{ ticker: string; days_until: number }>;
  onOpenCalendar?: () => void;
}) {
  const now = Date.now();
  const week = events
    .map((e) => ({ e, d: eventDate(e) }))
    .filter(({ d }) => d && d.getTime() >= now - 86_400_000 && d.getTime() <= now + 7 * 86_400_000)
    .sort((a, b) => a.d!.getTime() - b.d!.getTime());
  const seen = new Set<string>();
  const macroChips = week
    .map(({ e, d }) => ({ name: String(e.event ?? e.name ?? "").trim(), d: d! }))
    .filter((x) => x.name && !seen.has(x.name) && seen.add(x.name))
    .slice(0, 6);
  const earn = heldEarnings.filter((x) => x.days_until >= 0 && x.days_until <= 7).sort((a, b) => a.days_until - b.days_until);
  return (
    <Card
      title="This week"
      right={
        onOpenCalendar && (
          <button type="button" onClick={onOpenCalendar} className="text-[11.5px] font-semibold text-td-accent">
            Calendar ›
          </button>
        )
      }
    >
      {macroChips.length || earn.length ? (
        <div className="flex flex-wrap gap-1.5">
          {macroChips.map((c) => (
            <span key={c.name} className="rounded-full bg-td-surface2 px-2.5 py-1 text-[11.5px] font-semibold text-td-text/85" title={c.d.toDateString()}>
              {c.name.length > 26 ? `${c.name.slice(0, 25)}…` : c.name}
              <span className="text-td-muted font-normal"> · {c.d.toLocaleDateString("en-US", { weekday: "short" })}</span>
            </span>
          ))}
          {earn.map((x) => (
            <span key={x.ticker} className="rounded-full bg-td-warn-weak px-2.5 py-1 text-[11.5px] font-semibold text-td-warn">
              {x.ticker} earnings · {x.days_until === 0 ? "today" : `${x.days_until}d`} · held
              {x.days_until <= 2 ? " · size down" : ""}
            </span>
          ))}
        </div>
      ) : (
        <p className="text-[12px] text-td-muted">No scheduled macro events or held-name earnings in the next 7 days.</p>
      )}
    </Card>
  );
}

// ── Weather teaser + catalyst strip ─────────────────────────────────────────

export function MarketWeatherTeaser({
  weather,
  onOpen,
  cautions = [],
}: {
  weather: MarketWeather;
  onOpen?: () => void;
  /** Config/macro guidelines (spec positioning, real yields, macro week) — folded in, not stacked banners. */
  cautions?: string[];
}) {
  const st = WEATHER_STYLE[weather.tone];
  const [open, setOpen] = useState(false);
  return (
    <section className={clsx("rounded-2xl border px-4 py-3", st.box)}>
      <button type="button" onClick={onOpen} className="w-full text-left">
        <span className={clsx("flex items-center justify-between gap-2 text-[13px] font-bold", st.text)}>
          <span className="flex items-center gap-2">
            <span className={clsx("h-2 w-2 rounded-full", st.dot)} />
            Market weather: {weather.label}
          </span>
          <span className="flex items-center gap-0.5 text-[11px] font-semibold opacity-90">
            Markets <ChevronRight className="h-3.5 w-3.5" />
          </span>
        </span>
        {weather.detail && <span className="mt-1 block text-[12px] text-td-text/80 leading-snug">{weather.detail}</span>}
      </button>
      {cautions.length > 0 && (
        <div className="mt-1.5">
          <button
            type="button"
            onClick={() => setOpen((o) => !o)}
            aria-expanded={open}
            className="text-[11.5px] font-semibold text-td-warn hover:brightness-110"
          >
            {open ? "Hide cautions" : `${cautions.length} caution${cautions.length === 1 ? "" : "s"} this week ›`}
          </button>
          {open && (
            <ul className="mt-1.5 space-y-1 text-[12px] text-td-text/85 leading-snug list-disc pl-4">
              {cautions.map((c) => (
                <li key={c}>{c}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}

export function CatalystStrip({ ticker, daysUntil, onClick }: { ticker: string; daysUntil: number; onClick?: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="w-full text-left rounded-2xl border border-td-warn/30 bg-td-warn-weak/70 px-4 py-2.5 text-[12px] font-semibold text-td-warn hover:brightness-110"
    >
      CATALYST — {ticker} earnings {daysUntil === 0 ? "today" : `in ${daysUntil}d`}: size down into the print
    </button>
  );
}

export function PortfolioTeaser({
  totalValue,
  holdingCount,
  largest,
  onOpen,
}: {
  totalValue: number | null | undefined;
  holdingCount: number;
  largest?: { ticker: string; pct: number } | null;
  onOpen?: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onOpen}
      className="w-full flex items-center justify-between gap-3 rounded-2xl border border-td-line bg-td-surface px-4 py-3 text-left hover:border-td-accent/40"
    >
      <span className="text-[12.5px] text-td-muted">
        Portfolio{" "}
        <span className="font-mono font-semibold text-td-text">
          {totalValue != null ? `$${Math.round(totalValue).toLocaleString()}` : "—"}
        </span>
        {" · "}
        {holdingCount} holdings
        {largest ? ` · largest ${largest.ticker} ${largest.pct.toFixed(1)}%` : ""}
      </span>
      <span className="flex items-center text-[11.5px] font-semibold text-td-accent shrink-0">
        Summary & risk <ChevronRight className="h-3.5 w-3.5" />
      </span>
    </button>
  );
}
