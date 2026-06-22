"use client";

import { useEffect, useState } from "react";
import { Info, Clock } from "lucide-react";
import { clsx } from "clsx";
import { formatSnapshotAge, formatSnapshotEt, snapshotAgeTone } from "@/lib/dashboardCache";

export type DataFreshness = {
  as_of_et?: string;
  snapshot_updated_at?: string | null;
  snapshot_updated_et?: string | null;
  eod_snapshot_saved_at?: string | null;
  serving_stale?: boolean;
  snapshot_source?: "cache" | "last_snapshot" | "live" | string;
  refresh_status?: string;
  status?: string;
  message?: string;
  /** ISO timestamps for split quote vs signal freshness (Phase 1 retail refresh) */
  quotes_updated_at?: string | null;
  signals_updated_at?: string | null;
  prices?: string;
  fundamentals?: string;
  macro?: string;
  disclaimer?: string;
  /** Latest daily bar date across scanned tickers (YYYY-MM-DD) */
  price_last_bar_date?: string | null;
  /** Date string from most recent EOD snapshot row, if any */
  eod_snapshot_latest_date?: string | null;
  /** Short copy: targets/stops are ranges, not guaranteed prices */
  precision_note?: string | null;
};

function SnapshotMetaLine({
  data,
  compact,
}: {
  data: DataFreshness;
  compact?: boolean;
}) {
  const snapshotIso = data.snapshot_updated_at ?? data.as_of_et;
  const [age, setAge] = useState(() => formatSnapshotAge(snapshotIso));
  const [tone, setTone] = useState(() => snapshotAgeTone(snapshotIso));

  useEffect(() => {
    const tick = () => {
      setAge(formatSnapshotAge(snapshotIso));
      setTone(snapshotAgeTone(snapshotIso));
    };
    tick();
    const id = setInterval(tick, 60000);
    return () => clearInterval(id);
  }, [snapshotIso]);

  if (data.status === "warming") {
    return <p className="text-amber-200/90">{data.message ?? "First dashboard compute in progress…"}</p>;
  }

  const quotesIso = data.quotes_updated_at ?? null;
  const signalsIso = data.signals_updated_at ?? null;
  const hasSplitFreshness = Boolean(quotesIso || signalsIso);

  if (hasSplitFreshness) {
    const quotesLabel = formatSnapshotEt(quotesIso) || "—";
    const signalsLabel = formatSnapshotEt(signalsIso) || "—";
    return (
      <div className={clsx("flex flex-wrap items-center gap-x-2 gap-y-1", compact ? "text-xs" : "text-sm")}>
        <Clock className="h-3.5 w-3.5 text-slate-500 shrink-0" aria-hidden />
        <span className="text-slate-400">Prices as of</span>
        <span className="font-mono text-slate-200">{quotesLabel}</span>
        <span className="text-slate-600">·</span>
        <span className="text-slate-400">Signals as of</span>
        <span className="font-mono text-slate-200">{signalsLabel}</span>
        {data.serving_stale && (
          <span className="text-[10px] uppercase tracking-wide font-semibold text-amber-300 border border-amber-500/40 bg-amber-500/10 px-1.5 py-0.5 rounded">
            Stale — refreshing
          </span>
        )}
      </div>
    );
  }

  const timeLabel = data.snapshot_updated_et ?? formatSnapshotEt(snapshotIso);
  const stale = data.serving_stale || tone === "stale";

  return (
    <div className={clsx("flex flex-wrap items-center gap-x-2 gap-y-1", compact ? "text-xs" : "text-sm")}>
      <Clock className="h-3.5 w-3.5 text-slate-500 shrink-0" aria-hidden />
      <span className="text-slate-400">Snapshot updated</span>
      <span className="font-mono text-slate-200">{timeLabel}</span>
      {age && (
        <span
          className={clsx(
            "font-medium",
            tone === "fresh" && "text-emerald-400/90",
            tone === "aging" && "text-amber-300/90",
            tone === "stale" && "text-amber-400",
          )}
        >
          ({age})
        </span>
      )}
      {data.serving_stale && (
        <span className="text-[10px] uppercase tracking-wide font-semibold text-amber-300 border border-amber-500/40 bg-amber-500/10 px-1.5 py-0.5 rounded">
          Stale — refreshing
        </span>
      )}
      {!data.serving_stale && stale && age && (
        <span className="text-[10px] text-amber-400/90">may be outdated</span>
      )}
      {!compact && data.snapshot_source && (
        <span className="text-slate-600 text-[10px]">source: {data.snapshot_source.replace("_", " ")}</span>
      )}
    </div>
  );
}

/** As-of + snapshot staleness — trust strip for retail. */
export function DataFreshnessBar({
  data,
  compact = false,
}: {
  data: DataFreshness;
  compact?: boolean;
}) {
  if (compact) {
    return (
      <div
        className="rounded-lg border border-slate-700/80 bg-slate-900/50 px-3 py-2 text-xs text-slate-400 flex flex-wrap items-center gap-x-3 gap-y-1"
        title="When the dashboard snapshot was last saved on the server"
      >
        <SnapshotMetaLine data={data} compact />
        {(data.price_last_bar_date || data.eod_snapshot_latest_date) && (
          <span className="text-slate-600 hidden sm:inline">
            {data.price_last_bar_date && <>Bar {data.price_last_bar_date}</>}
            {data.price_last_bar_date && data.eod_snapshot_latest_date && " · "}
            {data.eod_snapshot_latest_date && <>EOD {data.eod_snapshot_latest_date}</>}
          </span>
        )}
      </div>
    );
  }

  return (
    <div
      className="rounded-lg border border-slate-600/80 bg-slate-800/40 px-3 py-2.5 text-xs text-slate-400 flex flex-wrap items-start gap-2"
      title={[data.prices, data.fundamentals, data.macro].filter(Boolean).join(" ")}
    >
      <Info className="h-4 w-4 text-slate-500 shrink-0 mt-0.5" aria-hidden />
      <div className="min-w-0 space-y-1.5">
        <SnapshotMetaLine data={data} />
        {(data.price_last_bar_date || data.eod_snapshot_latest_date || data.eod_snapshot_saved_at) && (
          <p className="text-slate-500 leading-snug">
            {data.price_last_bar_date && (
              <span>
                Last price bar: <span className="font-mono text-slate-400">{data.price_last_bar_date}</span>
              </span>
            )}
            {data.price_last_bar_date && data.eod_snapshot_latest_date && <span className="text-slate-600"> · </span>}
            {data.eod_snapshot_latest_date && (
              <span>
                EOD snapshot: <span className="font-mono text-slate-400">{data.eod_snapshot_latest_date}</span>
              </span>
            )}
            {data.eod_snapshot_saved_at && (
              <span className="block sm:inline sm:ml-0">
                {data.price_last_bar_date || data.eod_snapshot_latest_date ? (
                  <span className="hidden sm:inline text-slate-600"> · </span>
                ) : null}
                EOD saved: <span className="font-mono text-slate-400">{formatSnapshotEt(String(data.eod_snapshot_saved_at))}</span>
              </span>
            )}
          </p>
        )}
        <p className="text-slate-500 leading-snug">
          <span className="text-slate-600">Computed at run time — </span>
          {data.fundamentals && <span>{data.fundamentals} </span>}
          {data.disclaimer && <span className="text-slate-600">— {data.disclaimer}</span>}
        </p>
        {data.precision_note && <p className="text-slate-600 leading-snug">{data.precision_note}</p>}
      </div>
    </div>
  );
}
