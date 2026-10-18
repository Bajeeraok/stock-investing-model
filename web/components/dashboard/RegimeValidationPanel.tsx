"use client";

/**
 * Admin → regime_validation. The dashboard bundle has always carried this field but nothing
 * rendered it; the redesign surfaces it here instead of silently dropping it. The payload is
 * loosely typed (validated: unknown), so this renders the summary plus whatever flat
 * key/value or row-list shape `validated` arrives in.
 */

import { ShieldCheck } from "lucide-react";

type Props = { data?: { validated?: unknown; summary?: string; error?: boolean } | null };

function fmt(v: unknown): string {
  if (v == null) return "—";
  if (typeof v === "number") return Number.isInteger(v) ? String(v) : v.toFixed(3);
  if (typeof v === "boolean") return v ? "yes" : "no";
  if (typeof v === "string") return v;
  return JSON.stringify(v);
}

export function RegimeValidationPanel({ data }: Props) {
  if (!data || (!data.summary && data.validated == null)) return null;
  const v = data.validated;
  const rows: Array<Record<string, unknown>> = Array.isArray(v)
    ? (v.filter((r) => r && typeof r === "object") as Array<Record<string, unknown>>)
    : [];
  const flat: Array<[string, unknown]> =
    !Array.isArray(v) && v && typeof v === "object" ? Object.entries(v as Record<string, unknown>) : [];
  const cols = rows.length ? Array.from(new Set(rows.flatMap((r) => Object.keys(r)))).slice(0, 6) : [];

  return (
    <section className="rounded-xl border border-slate-700 bg-slate-800/30 p-4 space-y-2">
      <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-200">
        <ShieldCheck className="h-4 w-4 text-violet-400" />
        Regime validation
        {data.error && <span className="text-[11px] font-normal text-amber-300">(last run reported an error)</span>}
      </h3>
      {data.summary && <p className="text-sm text-slate-400 leading-snug">{data.summary}</p>}
      {flat.length > 0 && (
        <dl className="grid grid-cols-2 sm:grid-cols-3 gap-x-4 gap-y-1 text-xs">
          {flat.slice(0, 18).map(([k, val]) => (
            <div key={k} className="flex justify-between gap-2 border-b border-slate-700/40 py-1">
              <dt className="text-slate-500 truncate">{k.replace(/_/g, " ")}</dt>
              <dd className="font-mono text-slate-300 truncate">{fmt(val)}</dd>
            </div>
          ))}
        </dl>
      )}
      {rows.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-xs text-left min-w-[420px]">
            <thead>
              <tr className="text-slate-500 border-b border-slate-700">
                {cols.map((c) => (
                  <th key={c} className="py-1 pr-3 font-medium">{c.replace(/_/g, " ")}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.slice(0, 20).map((r, i) => (
                <tr key={i} className="border-b border-slate-800 text-slate-300">
                  {cols.map((c) => (
                    <td key={c} className="py-1 pr-3 font-mono">{fmt(r[c])}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
