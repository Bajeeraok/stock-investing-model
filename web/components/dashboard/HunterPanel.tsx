"use client";

import { useEffect, useMemo, useState } from "react";
import { Crosshair } from "lucide-react";
import { clsx } from "clsx";
import { PossessionBadge, type PositionStatus } from "./PossessionBadge";
import { paginateRows, TablePager } from "./TablePager";
import {
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

const PAGE_SIZE = 20;

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

const REASON_STYLE: Record<HunterReason, string> = {
  velocity: "bg-violet-500/15 text-violet-300 border-violet-500/30",
  go_ready: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
  almost_ready: "bg-sky-500/15 text-sky-300 border-sky-500/30",
  warming: "bg-amber-500/15 text-amber-300 border-amber-500/30",
};

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
  const [page, setPage] = useState(0);
  const [customScreens, setCustomScreens] = useState<CustomHunterScreen[]>([]);

  useEffect(() => {
    setScreen(loadHunterScreen());
    setCustomScreens(loadCustomHunterScreens());
  }, []);

  const portfolioSet = useMemo(() => toTickerSet(portfolioTickers), [portfolioTickers]);
  const watchlistSet = useMemo(() => toTickerSet(watchlistTickers), [watchlistTickers]);

  const allCandidates = panel?.candidates ?? [];

  const filtered = useMemo(() => {
    let rows = filterHunterCandidates(allCandidates, screen);
    const tickers = rows.map((r) => r.ticker);
    const kept = new Set(
      filterTickersBySource(tickers, source, portfolioSet, watchlistSet).map((t) => t.toUpperCase()),
    );
    rows = rows.filter((r) => kept.has(r.ticker.toUpperCase()));
    return rows;
  }, [allCandidates, screen, source, portfolioSet, watchlistSet]);

  useEffect(() => {
    setPage(0);
  }, [screen, source]);

  const paged = useMemo(() => paginateRows(filtered, page, PAGE_SIZE), [filtered, page]);

  const counts = panel?.counts;

  const handleScreen = (id: HunterScreenId) => {
    setScreen(id);
    saveHunterScreen(id);
  };

  return (
    <div className="rounded-xl border border-emerald-500/30 bg-gradient-to-b from-emerald-950/20 to-slate-900/40 p-4 space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="text-sm font-semibold text-slate-100 flex items-center gap-2">
            <Crosshair className="h-4 w-4 text-emerald-400 shrink-0" />
            Hunter panel
            <span className="text-emerald-300/90 tabular-nums font-normal">
              ({panel?.candidate_count ?? 0} setups)
            </span>
          </p>
          <p className="text-[11px] text-slate-500 mt-1 max-w-2xl leading-relaxed">
            {panel?.methodology ??
              "Your book (watchlist + portfolio) — tactical velocity or readiness tiers. Updates on Dashboard Refresh."}
          </p>
        </div>
        {panel?.as_of && (
          <span className="text-[10px] text-slate-500 font-mono">as of {panel.as_of.slice(0, 16)}</span>
        )}
      </div>

      {(counts?.velocity ?? 0) > 0 || (counts?.go_ready ?? 0) > 0 ? (
        <div className="flex flex-wrap gap-2 text-[11px]">
          {(counts?.velocity ?? 0) > 0 && (
            <span className="rounded-full border border-violet-500/35 px-2 py-0.5 text-violet-300 tabular-nums">
              Tactical {counts?.velocity}
            </span>
          )}
          {(counts?.go_ready ?? 0) > 0 && (
            <span className="rounded-full border border-emerald-500/35 px-2 py-0.5 text-emerald-300 tabular-nums">
              GO {counts?.go_ready}
            </span>
          )}
          {(counts?.almost_ready ?? 0) > 0 && (
            <span className="rounded-full border border-sky-500/35 px-2 py-0.5 text-sky-300 tabular-nums">
              Almost {counts?.almost_ready}
            </span>
          )}
          {(counts?.warming ?? 0) > 0 && (
            <span className="rounded-full border border-amber-500/35 px-2 py-0.5 text-amber-300 tabular-nums">
              Warming {counts?.warming}
            </span>
          )}
          {(counts?.not_in_portfolio ?? 0) > 0 && (
            <span className="rounded-full border border-slate-600 px-2 py-0.5 text-slate-400 tabular-nums">
              Not in book {counts?.not_in_portfolio}
            </span>
          )}
        </div>
      ) : null}

      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-[10px] text-slate-500 uppercase tracking-wide shrink-0">Screen</span>
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
        <span className="text-[10px] text-slate-500 uppercase tracking-wide shrink-0">Book</span>
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
        <span className="text-[10px] text-slate-600 tabular-nums ml-auto">
          {filtered.length}/{allCandidates.length} shown · universe {panel?.universe_size ?? "—"}
        </span>
      </div>

      {panel?.message && (
        <p className="text-xs text-amber-200/90 border border-amber-500/30 rounded-lg px-3 py-2">{panel.message}</p>
      )}

      {filtered.length === 0 ? (
        <p className="text-sm text-slate-500">
          No names match this screen right now. Cache refresh picks up new readiness / tactical flags.
        </p>
      ) : (
        <div className="overflow-x-auto [-webkit-overflow-scrolling:touch]">
          <table className="w-full text-xs text-left min-w-[640px]">
            <thead>
              <tr className="text-slate-500 border-b border-slate-600">
                <th className="py-1.5 pr-2 font-medium">Ticker</th>
                <th className="py-1.5 pr-2 font-medium">Book</th>
                <th className="py-1.5 pr-2 font-medium">Setup</th>
                <th className="py-1.5 pr-2 font-medium">Gates</th>
                <th className="py-1.5 pr-2 font-medium">Track</th>
                <th className="py-1.5 pr-2 font-medium">Score</th>
                <th className="py-1.5 pr-2 font-medium">Signal</th>
              </tr>
            </thead>
            <tbody>
              {paged.map((r) => (
                <tr key={r.ticker} className="border-b border-slate-700/50 text-slate-300">
                  <td className="py-1 pr-2">
                    <button
                      type="button"
                      onClick={() => onTickerClick?.(r.ticker)}
                      className="font-mono font-medium text-emerald-200 hover:underline"
                    >
                      {r.ticker}
                    </button>
                  </td>
                  <td className="py-1 pr-2">
                    <PossessionBadge status={r.position_status} />
                  </td>
                  <td className="py-1 pr-2">
                    <span
                      className={clsx(
                        "px-1.5 py-0.5 rounded text-[10px] border uppercase",
                        REASON_STYLE[r.hunter_reason],
                      )}
                    >
                      {REASON_LABEL[r.hunter_reason]}
                    </span>
                  </td>
                  <td className="py-1 pr-2 tabular-nums">
                    {r.gates_passed ?? "—"}/{r.gates_total ?? 4}
                  </td>
                  <td className="py-1 pr-2 uppercase text-[10px] text-slate-400">{r.track ?? "—"}</td>
                  <td className="py-1 pr-2 tabular-nums">{r.composite_buy?.toFixed(0) ?? "—"}</td>
                  <td className="py-1 pr-2">{r.signal ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <TablePager page={page} pageSize={PAGE_SIZE} total={filtered.length} onPageChange={setPage} />

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
