"use client";

import { useEffect, useMemo, useState } from "react";
import { SlidersHorizontal } from "lucide-react";
import { clsx } from "clsx";
import { PossessionBadge } from "./PossessionBadge";
import {
  type HunterCall,
  BUILTIN_HUNTER_SCREENS,
  filterHunterCandidates,
  loadCustomHunterScreens,
  loadHunterScreen,
  saveCustomHunterScreens,
  saveHunterScreen,
  type CustomHunterScreen,
  type HunterCandidate,
  type HunterReason,
  type HunterScreenId,
} from "@/lib/hunterScreens";
import {
  TICKER_SOURCE_FILTERS,
  filterTickersBySource,
  toTickerSet,
  type TickerSourceFilter,
} from "@/lib/tickerSourceFilter";

const GROUP_PREVIEW = 6;

export type { HunterCandidate, HunterReason } from "@/lib/hunterScreens";

export type HunterPanelPayload = {
  as_of?: string | null;
  universe_size?: number;
  candidate_count?: number;
  counts?: {
    velocity?: number;
    go_ready?: number;
    almost_ready?: number;
    warming?: number;
    not_in_portfolio?: number;
  };
  candidates?: HunterCandidate[];
  methodology?: string | null;
  message?: string | null;
};

const REASON_LABEL: Record<HunterReason, string> = {
  velocity: "Tactical",
  go_ready: "GO 4/4",
  almost_ready: "Almost",
  warming: "Warming",
};

type DisplayTier = HunterReason | "avoid";

/** Readiness tiers in reading order — same 4 primary gates as the ticker Verdict/Why tabs.
 * "avoid" is last: names whose model action or trend is against them, whatever the gate count. */
const TIERS: { id: DisplayTier; chip: string; title: string; hint: string; chipOn: string; head: string }[] = [
  { id: "velocity", chip: "Tactical", title: "Tactical", hint: "velocity breakout — not full GO", chipOn: "bg-td-owner-weak text-td-owner", head: "text-td-owner" },
  { id: "go_ready", chip: "GO", title: "GO · all gates green", hint: "4/4 gates", chipOn: "bg-td-accent-weak text-td-accent", head: "text-td-accent" },
  { id: "almost_ready", chip: "Almost", title: "Almost ready", hint: "3/4 gates", chipOn: "bg-td-info/15 text-td-info", head: "text-td-info" },
  { id: "warming", chip: "Warming", title: "Warming", hint: "3/4 gates, short-term not confirming", chipOn: "bg-td-warn-weak text-td-warn", head: "text-td-warn" },
  { id: "avoid", chip: "Avoid", title: "Avoid for now", hint: "model or trend against — gate count doesn't matter", chipOn: "bg-td-crit-weak text-td-crit", head: "text-td-crit" },
];

const CALL_BADGE: Record<HunterCall, { label: string; cls: string }> = {
  buy: { label: "BUY", cls: "bg-td-accent-weak text-td-accent" },
  tactical: { label: "TACTICAL", cls: "bg-td-owner-weak text-td-owner" },
  wait: { label: "WAIT", cls: "bg-td-warn-weak text-td-warn" },
  avoid: { label: "AVOID", cls: "bg-td-crit-weak text-td-crit" },
};

/** Older cached payloads predate the backend call — derive the same thing conservatively. */
function resolveCall(r: HunterCandidate): { call: HunterCall; reason: string; tier: DisplayTier } {
  if (r.call) return { call: r.call, reason: r.call_reason ?? "", tier: r.display_tier ?? r.hunter_reason };
  const pa = (r.plan_action || "").toUpperCase();
  const total = r.gates_total ?? 4;
  const missing = total - (r.gates_passed ?? 0);
  const score = r.composite_buy;
  const down = (r.regime || "").toUpperCase() === "DOWN";
  if (down && ((score != null && score < 35) || (r.rsi != null && r.rsi < 30 && (score == null || score < 50)))) {
    return { call: "avoid", reason: "Falling-knife risk — weak score in a downtrend. Wait for the trend to turn.", tier: "avoid" };
  }
  if (/REDUCE|AVOID|SELL|TRIM/.test(pa)) return { call: "avoid", reason: `Model says ${pa} — don't add.`, tier: "avoid" };
  if (r.hunter_reason === "velocity") return { call: "tactical", reason: "Short-term breakout — starter size with a tight stop.", tier: "velocity" };
  if ((r.gate_cleared || missing <= 0) && /BUY|ADD/.test(pa)) return { call: "buy", reason: "All gates green and the model agrees.", tier: r.hunter_reason };
  return { call: "wait", reason: `${Math.max(0, missing)} more gate(s) or a model BUY needed first.`, tier: r.hunter_reason };
}

function GateBar({ passed, total }: { passed: number; total: number }) {
  return (
    <div className="flex gap-[3px]" aria-label={`${passed} of ${total} gates pass`}>
      {Array.from({ length: total }).map((_, i) => (
        <span key={i} className={clsx("h-1 flex-1 rounded-full", i < passed ? "bg-td-accent" : "bg-td-surface2")} />
      ))}
    </div>
  );
}

function HunterCard({ r, onTickerClick }: { r: HunterCandidate; onTickerClick?: (ticker: string) => void }) {
  const total = r.gates_total ?? 4;
  const passed = Math.max(0, Math.min(total, r.gates_passed ?? 0));
  const { call, reason } = resolveCall(r);
  const badge = CALL_BADGE[call];
  const model = (r.plan_action || "").replace(/_/g, " ").trim();
  const facts = [
    `${passed}/${total} gates`,
    model ? `model ${model}` : null,
    r.velocity_triggered || r.track === "velocity"
      ? `Velocity${r.velocity_score != null ? ` ${Math.round(r.velocity_score)}` : ""}`
      : null,
    r.rsi != null ? `RSI ${Math.round(r.rsi)}` : null,
    r.regime ? `${r.regime.charAt(0)}${r.regime.slice(1).toLowerCase()} trend` : null,
  ].filter(Boolean);
  return (
    <button
      type="button"
      onClick={() => onTickerClick?.(r.ticker)}
      className={clsx(
        "w-full text-left rounded-xl border bg-td-surface px-3.5 py-3 transition-colors hover:bg-td-surface2/50",
        r.position_status === "owned" ? "border-td-owner/50" : "border-td-line",
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-2 min-w-0">
          <span className="font-mono text-[14px] font-bold text-td-text">{r.ticker}</span>
          <PossessionBadge status={r.position_status} />
        </span>
        <span className="flex items-center gap-2 shrink-0">
          {r.composite_buy != null && (
            <span className="font-mono text-[11px] text-td-muted tabular-nums">Score {r.composite_buy.toFixed(0)}</span>
          )}
          <span className={clsx("font-mono text-[10.5px] font-bold px-2 py-0.5 rounded-full", badge.cls)}>{badge.label}</span>
        </span>
      </div>
      <div className="mt-2">
        <GateBar passed={passed} total={total} />
      </div>
      <p className="mt-1.5 text-[11.5px] text-td-muted">{facts.join(" · ")}</p>
      <p
        className={clsx(
          "mt-1 text-[11.5px]",
          call === "buy" ? "text-td-accent" : call === "avoid" ? "text-td-crit" : call === "tactical" ? "text-td-owner" : "text-td-info",
        )}
      >
        {reason}
        {r.hunter_reason === "velocity" && r.tactical_t1 != null ? ` · T1 $${r.tactical_t1.toFixed(2)}` : ""}
        {r.hunter_reason === "velocity" && r.tactical_stop != null ? ` · stop $${r.tactical_stop.toFixed(2)}` : ""}
        {" ›"}
      </p>
    </button>
  );
}

export function HunterPanel({
  panel,
  portfolioTickers,
  watchlistTickers,
  onTickerClick,
  source,
  onSourceChange,
}: {
  panel: HunterPanelPayload | null | undefined;
  portfolioTickers?: string[];
  watchlistTickers?: string[];
  onTickerClick?: (ticker: string) => void;
  /** Book filter now owned by the Signals hub's shared filter bar. */
  source: TickerSourceFilter;
  onSourceChange: (id: TickerSourceFilter) => void;
}) {
  const [screen, setScreen] = useState<HunterScreenId>("all_hunt");
  const [customScreens, setCustomScreens] = useState<CustomHunterScreen[]>([]);
  const [tierFilter, setTierFilter] = useState<DisplayTier | null>(null);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [expanded, setExpanded] = useState<Partial<Record<DisplayTier, boolean>>>({});

  useEffect(() => {
    setScreen(loadHunterScreen());
    setCustomScreens(loadCustomHunterScreens());
  }, []);

  const portfolioSet = useMemo(() => toTickerSet(portfolioTickers), [portfolioTickers]);
  const watchlistSet = useMemo(() => toTickerSet(watchlistTickers), [watchlistTickers]);

  const allCandidates = panel?.candidates ?? [];

  /** Screen + book filters (the Filters sheet) — tier chips then slice this. */
  const filtered = useMemo(() => {
    let rows = filterHunterCandidates(allCandidates, screen);
    const tickers = rows.map((r) => r.ticker);
    const kept = new Set(
      filterTickersBySource(tickers, source, portfolioSet, watchlistSet).map((t) => t.toUpperCase()),
    );
    rows = rows.filter((r) => kept.has(r.ticker.toUpperCase()));
    return rows;
  }, [allCandidates, screen, source, portfolioSet, watchlistSet]);

  const byTier = useMemo(() => {
    const m: Record<DisplayTier, HunterCandidate[]> = { velocity: [], go_ready: [], almost_ready: [], warming: [], avoid: [] };
    for (const r of filtered) m[resolveCall(r).tier]?.push(r);
    return m;
  }, [filtered]);

  const shownCount = tierFilter ? byTier[tierFilter].length : filtered.length;

  const handleScreen = (id: HunterScreenId) => {
    setScreen(id);
    saveHunterScreen(id);
  };

  const activeFilterCount = (screen !== "all_hunt" ? 1 : 0) + (source !== "all" ? 1 : 0);
  let asOf: string | null = null;
  if (panel?.as_of) {
    const d = new Date(panel.as_of);
    asOf = Number.isNaN(d.getTime())
      ? panel.as_of.slice(0, 16)
      : `${d.toLocaleTimeString("en-US", { timeZone: "America/New_York", hour: "numeric", minute: "2-digit" })} ET`;
  }

  return (
    <div className="space-y-3">
      {/* Tier chips + Filters */}
      <div className="flex items-center gap-1.5 overflow-x-auto pb-0.5">
        {TIERS.map((t) => {
          const n = byTier[t.id].length;
          const on = tierFilter === t.id;
          return (
            <button
              key={t.id}
              type="button"
              onClick={() => setTierFilter(on ? null : t.id)}
              aria-pressed={on}
              title={t.hint}
              className={clsx(
                "shrink-0 rounded-full px-3 py-1.5 text-[12px] font-semibold transition-colors",
                on ? t.chipOn : "bg-td-surface2/70 text-td-muted hover:text-td-text",
                n === 0 && !on && "opacity-50",
              )}
            >
              {t.chip} {n}
            </button>
          );
        })}
        <button
          type="button"
          onClick={() => setFiltersOpen((o) => !o)}
          aria-expanded={filtersOpen}
          className={clsx(
            "ml-auto shrink-0 inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[12px] font-semibold",
            filtersOpen || activeFilterCount ? "bg-td-surface2 text-td-text" : "text-td-muted hover:text-td-text",
          )}
        >
          <SlidersHorizontal className="h-3.5 w-3.5" />
          Filters{activeFilterCount ? ` · ${activeFilterCount}` : ""}
        </button>
      </div>

      <p className="text-[11px] text-td-muted">
        {shownCount} of {panel?.universe_size ?? allCandidates.length}
        {" · "}
        {source === "portfolio" ? "owning" : source === "watchlist_only" ? "watching" : "your book"}
        {asOf ? ` · as of ${asOf}` : ""}
      </p>

      {filtersOpen && (
        <div className="rounded-xl border border-td-line bg-td-surface p-3 space-y-3">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-[10px] text-td-muted uppercase tracking-wide shrink-0 w-12">Screen</span>
            {BUILTIN_HUNTER_SCREENS.map((s) => (
              <button
                key={s.id}
                type="button"
                title={s.hint}
                onClick={() => handleScreen(s.id)}
                className={clsx(
                  "text-[11px] px-2 py-1 rounded-full border shrink-0",
                  screen === s.id
                    ? "border-emerald-500/45 bg-emerald-500/15 text-emerald-200"
                    : "border-slate-600 text-slate-400 hover:text-slate-200",
                )}
              >
                {s.label}
              </button>
            ))}
            {customScreens.map((c) => (
              <button
                key={c.id}
                type="button"
                onClick={() => handleScreen(`custom:${c.id}` as HunterScreenId)}
                className={clsx(
                  "text-[11px] px-2 py-1 rounded-full border shrink-0",
                  screen === `custom:${c.id}`
                    ? "border-emerald-500/45 bg-emerald-500/15 text-emerald-200"
                    : "border-slate-600 text-slate-400",
                )}
              >
                {c.label}
              </button>
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-[10px] text-td-muted uppercase tracking-wide shrink-0 w-12">Book</span>
            {TICKER_SOURCE_FILTERS.map((f) => (
              <button
                key={f.id}
                type="button"
                title={f.hint}
                onClick={() => onSourceChange(f.id)}
                className={clsx(
                  "text-[11px] px-2 py-1 rounded-full border shrink-0",
                  source === f.id
                    ? "border-sky-500/45 bg-sky-500/15 text-sky-200"
                    : "border-slate-600 text-slate-400 hover:text-slate-200",
                )}
              >
                {f.id === "portfolio" ? "Owning" : f.id === "watchlist_only" ? "Watching" : f.label}
              </button>
            ))}
          </div>
          <details className="text-[11px] text-slate-500">
            <summary className="cursor-pointer hover:text-slate-400">Save custom screen (max 2)</summary>
            <CustomScreenEditor
              screens={customScreens}
              onChange={(next) => {
                setCustomScreens(next);
                saveCustomHunterScreens(next);
              }}
            />
          </details>
          <p className="text-[10.5px] text-td-muted leading-snug">
            {panel?.methodology ??
              "Your book (watchlist + portfolio) — tactical velocity or readiness tiers. Updates on Dashboard Refresh."}
          </p>
        </div>
      )}

      {panel?.message && (
        <p className="text-xs text-amber-200/90 border border-amber-500/30 rounded-lg px-3 py-2">{panel.message}</p>
      )}

      {filtered.length === 0 ? (
        <p className="text-sm text-td-muted">
          No names match this screen right now. Cache refresh picks up new readiness / tactical flags.
        </p>
      ) : (
        <div className="space-y-5">
          {TIERS.filter((t) => (tierFilter ? t.id === tierFilter : true)).map((t) => {
            const rows = byTier[t.id];
            if (!rows.length) return null;
            const open = expanded[t.id] || tierFilter === t.id;
            const visible = open ? rows : rows.slice(0, GROUP_PREVIEW);
            return (
              <section key={t.id} aria-label={t.title}>
                <div className="flex items-baseline justify-between gap-2 mb-2">
                  <h4 className={clsx("text-[11.5px] font-bold uppercase tracking-wider", t.head)}>
                    {t.title} · {rows.length}
                  </h4>
                  <span className="text-[11px] text-td-muted">{t.hint}</span>
                </div>
                <div className="grid gap-2 sm:grid-cols-2 2xl:grid-cols-3">
                  {visible.map((r) => (
                    <HunterCard key={r.ticker} r={r} onTickerClick={onTickerClick} />
                  ))}
                </div>
                {rows.length > GROUP_PREVIEW && tierFilter !== t.id && (
                  <button
                    type="button"
                    onClick={() => setExpanded((e) => ({ ...e, [t.id]: !e[t.id] }))}
                    className="mt-2 text-[11.5px] font-semibold text-td-accent"
                  >
                    {open ? "Show fewer" : `Show all ${rows.length} ›`}
                  </button>
                )}
              </section>
            );
          })}
        </div>
      )}
    </div>
  );
}

function CustomScreenEditor({
  screens,
  onChange,
}: {
  screens: CustomHunterScreen[];
  onChange: (s: CustomHunterScreen[]) => void;
}) {
  const [label, setLabel] = useState("");
  const [reasons, setReasons] = useState<HunterReason[]>(["go_ready", "velocity"]);

  const add = () => {
    if (!label.trim() || screens.length >= 2) return;
    const id = `u${Date.now()}`;
    onChange([...screens, { id, label: label.trim(), reasons }]);
    setLabel("");
  };

  return (
    <div className="mt-2 space-y-2 rounded border border-slate-700/60 p-2">
      <input
        value={label}
        onChange={(e) => setLabel(e.target.value)}
        placeholder="Screen name"
        className="w-full rounded border border-slate-600 bg-slate-900 px-2 py-1 text-xs text-slate-200"
      />
      <div className="flex flex-wrap gap-1">
        {(["velocity", "go_ready", "almost_ready", "warming"] as HunterReason[]).map((r) => (
          <button
            key={r}
            type="button"
            onClick={() =>
              setReasons((prev) => (prev.includes(r) ? prev.filter((x) => x !== r) : [...prev, r]))
            }
            className={clsx(
              "text-[10px] px-2 py-0.5 rounded border",
              reasons.includes(r) ? "border-emerald-500/40 text-emerald-200" : "border-slate-600 text-slate-500",
            )}
          >
            {REASON_LABEL[r]}
          </button>
        ))}
      </div>
      <button
        type="button"
        onClick={add}
        disabled={screens.length >= 2}
        className="text-xs text-emerald-300 border border-emerald-500/40 rounded px-2 py-1 disabled:opacity-40"
      >
        Add screen
      </button>
      {screens.map((s) => (
        <div key={s.id} className="flex justify-between text-slate-400">
          <span>{s.label}</span>
          <button
            type="button"
            className="text-red-400/80"
            onClick={() => onChange(screens.filter((x) => x.id !== s.id))}
          >
            Remove
          </button>
        </div>
      ))}
    </div>
  );
}
