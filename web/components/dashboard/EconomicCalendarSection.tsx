"use client";

import { Calendar } from "lucide-react";
import type { EconomicCalendarEvent } from "@/app/page";

function fmt(v: unknown, unit: unknown): string {
  if (typeof v !== "number") return "—";
  const u = typeof unit === "string" && unit !== "" ? unit : "";
  return `${v}${u === "%" ? "%" : u ? ` ${u}` : ""}`;
}

function dayLabel(raw?: string): string {
  if (!raw) return "";
  const d = new Date(raw.length <= 10 ? `${raw}T12:00:00` : raw);
  return Number.isNaN(d.getTime()) ? raw.slice(0, 10) : d.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric", timeZone: "America/New_York" });
}

export function EconomicCalendarSection({ events }: { events: EconomicCalendarEvent[] }) {
  const title = (
    <h3 className="text-sm font-semibold text-slate-300 flex items-center gap-2 mb-2">
      <Calendar className="h-4 w-4 text-emerald-500" />
      US event calendar (next 7 days)
    </h3>
  );
  if (!events || events.length === 0) {
    return (
      <div className="rounded-xl border border-slate-700 bg-slate-900/50 p-4 min-w-0">
        {title}
        <p className="text-sm text-slate-500">No major US releases, Fed decisions or Treasury auctions scheduled.</p>
      </div>
    );
  }
  return (
    <div className="rounded-xl border border-slate-700 bg-slate-900/50 p-4 min-w-0">
      {title}
      <p className="text-[13px] text-slate-500 mb-2">Times ET. Surprise = actual − forecast. Context only; no signal uses it.</p>
      <ul className="divide-y divide-slate-800 text-sm">
        {events.slice(0, 30).map((e, i) => {
          const tier = typeof e.tier === "number" ? e.tier : 2;
          const surprise = typeof e.surprise === "number" ? e.surprise : null;
          return (
            <li key={i} className="py-1.5 flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
              <span className="w-28 shrink-0 text-[12px] text-slate-500 tabular-nums">
                {dayLabel(e.date)} {typeof e.time_et === "string" ? e.time_et : ""}
              </span>
              <span className={tier === 1 ? "font-semibold text-slate-100" : "text-slate-300"}>
                {tier === 1 && <span className="mr-1 rounded bg-amber-500/20 px-1 text-[10px] font-bold text-amber-300">HIGH</span>}
                {e.event || e.name}
                {typeof e.more === "number" && e.more > 0 && <span className="text-slate-500"> +{e.more}</span>}
              </span>
              {(e.estimate != null || e.actual != null) && (
                <span className="text-[12px] text-slate-400 tabular-nums">
                  fcst {fmt(e.estimate, e.unit)} · actual {fmt(e.actual, e.unit)}
                  {surprise != null && (
                    <span className={surprise > 0 ? "text-amber-300" : surprise < 0 ? "text-sky-300" : ""}> ({surprise > 0 ? "+" : ""}{surprise})</span>
                  )}
                </span>
              )}
              {typeof e.groups === "string" && <span className="basis-full pl-[7.5rem] text-[11px] text-slate-500">Moves: {e.groups}</span>}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
