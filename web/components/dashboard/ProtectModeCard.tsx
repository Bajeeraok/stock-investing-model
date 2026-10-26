"use client";

import React from "react";
import { clsx } from "clsx";
import { ShieldCheck } from "lucide-react";

export interface ProtectModePayload {
  available?: boolean;
  active?: boolean;
  suggested_position_pct?: number;
  default_action?: string;
  stock_below_ma200?: boolean | null;
  spy_risk_off?: boolean | null;
  reasons?: string[];
  headline?: string;
  note?: string;
}

/** Optional drawdown-insurance sizing; default guidance for an owned stock stays HOLD. */
export function ProtectModeCard({ data }: { data?: ProtectModePayload | null }) {
  if (!data || !data.available) return null;
  const active = !!data.active;
  return (
    <div
      className={clsx(
        "rounded-lg border px-3 py-2",
        active ? "border-td-warn/45 bg-td-warn/10" : "border-td-line/60 bg-td-line/10"
      )}
    >
      <div className="flex items-center gap-2">
        <ShieldCheck className={clsx("h-4 w-4 shrink-0", active ? "text-td-warn" : "text-td-muted")} aria-hidden />
        <p className="text-xs font-semibold uppercase tracking-wide text-td-text">
          Protect mode (optional) · {active ? `~${data.suggested_position_pct ?? 50}% position` : "full position"}
        </p>
      </div>
      {data.headline && <p className="text-[12px] text-td-text/90 mt-1 leading-snug">{data.headline}</p>}
      {active && (data.reasons?.length ?? 0) > 0 && (
        <ul className="mt-1 list-disc pl-5 text-[11px] text-td-text/80">
          {data.reasons!.map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
      )}
      {data.note && <p className="text-[11px] text-td-muted mt-1 leading-snug">{data.note}</p>}
    </div>
  );
}
