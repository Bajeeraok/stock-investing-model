"use client";

import { Calendar } from "lucide-react";
import type { EconomicCalendarEvent } from "@/app/page";

export function EconomicCalendarSection({ events }: { events: EconomicCalendarEvent[] }) {
  if (!events || events.length === 0) {
    return (
      <div className="rounded-xl border border-slate-700 bg-slate-900/50 p-4">
        <h3 className="text-sm font-semibold text-slate-300 flex items-center gap-2 mb-2">
          <Calendar className="h-4 w-4 text-emerald-500" />
          Event calendar (next 7 days)
        </h3>
        <p className="text-sm text-slate-500">No events. Add FMP API key (Starter+) for economic calendar.</p>
      </div>
    );
  }
  return (
    <div className="rounded-xl border border-slate-700 bg-slate-900/50 p-4">
      <h3 className="text-sm font-semibold text-slate-300 flex items-center gap-2 mb-3">
        <Calendar className="h-4 w-4 text-emerald-500" />
        Event calendar (next 7 days)
      </h3>
      <p className="text-xs text-slate-500 mb-2">CPI, FOMC, NFP, etc. – volatility/event risk flag.</p>
      <ul className="space-y-1.5 text-sm">
        {events.slice(0, 15).map((e, i) => (
          <li key={i} className="flex gap-2 text-slate-300">
            <span className="text-slate-500 shrink-0">{e.date || ""}</span>
            <span>{e.name || e.event || JSON.stringify(e).slice(0, 60)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
