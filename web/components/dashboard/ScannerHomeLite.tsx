"use client";

import { Radio } from "lucide-react";
import { clsx } from "clsx";

export type ScannerHomeAlert = {
  id?: string | null;
  ticker: string;
  alert_type?: string | null;
  priority?: string | null;
  message?: string | null;
  created_at?: string | null;
};

export type ScannerHomeLitePayload = {
  alerts?: ScannerHomeAlert[];
  alert_count?: number;
  universe_size?: number | null;
  message?: string | null;
};

const PRIORITY_STYLE: Record<string, string> = {
  CRITICAL: "text-red-300 border-red-500/40",
  HIGH: "text-amber-200 border-amber-500/40",
  MEDIUM: "text-sky-200 border-sky-500/40",
  LOW: "text-slate-400 border-slate-600",
};

export function ScannerHomeLite({
  data,
  onTickerClick,
}: {
  data: ScannerHomeLitePayload | null | undefined;
  onTickerClick?: (ticker: string) => void;
}) {
  const alerts = data?.alerts ?? [];
  if (!alerts.length) {
    return (
      <p className="text-xs text-slate-500 rounded-lg border border-slate-700/60 bg-slate-900/40 px-3 py-2">
        {data?.message ?? "Scanner alerts appear when the engine flags entry/stop/target levels."}
      </p>
    );
  }

  return (
    <div className="rounded-xl border border-cyan-500/25 bg-gradient-to-r from-cyan-950/30 to-slate-900/40 p-4">
      <div className="flex items-center gap-2 mb-2">
        <Radio className="h-4 w-4 text-cyan-400 shrink-0" />
        <p className="text-sm font-semibold text-cyan-100">Scanner highlights</p>
        <span className="text-[10px] text-slate-500 tabular-nums">
          {alerts.length} alert{alerts.length === 1 ? "" : "s"}
        </span>
      </div>
      <div className="flex flex-wrap gap-2">
        {alerts.map((a) => {
          const pr = String(a.priority ?? "MEDIUM").toUpperCase();
          return (
            <button
              key={a.id ?? `${a.ticker}-${a.created_at}`}
              type="button"
              onClick={() => onTickerClick?.(a.ticker)}
              className={clsx(
                "rounded-lg border bg-slate-900/60 px-2.5 py-1.5 text-left hover:opacity-90 touch-manipulation min-w-[8rem] max-w-[14rem]",
                PRIORITY_STYLE[pr] ?? PRIORITY_STYLE.MEDIUM,
              )}
            >
              <span className="font-mono text-sm">{a.ticker}</span>
              <p className="text-[10px] text-slate-400 mt-0.5 line-clamp-2">
                {a.message ?? a.alert_type ?? pr}
              </p>
            </button>
          );
        })}
      </div>
    </div>
  );
}
