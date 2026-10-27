"use client";

import type { LatestModelDaily } from "@/lib/useTickerTrackRecord";

function pct(n: number | null | undefined, digits = 2): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return `${n >= 0 ? "+" : ""}${n.toFixed(digits)}%`;
}

function tone(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "text-slate-500";
  return n >= 0 ? "text-emerald-400" : "text-red-400";
}

/**
 * Daily early read for the live model version — following its calls (full position, half on
 * TRIM/REDUCE) vs holding the same stock(s) vs SPY, compounded since the version's first clean
 * scored session. Complements, not replaces, the 20-day result.
 */
export default function LatestModelDailyCard({
  data,
  version,
  scope,
  maxRows = 10,
}: {
  data: LatestModelDaily | null | undefined;
  version: string | null | undefined;
  scope: "ticker" | "all";
  maxRows?: number;
}) {
  const v = data?.model_version || version;
  if (!v) return null;
  const days = data?.days ?? 0;
  const target = data?.target_days ?? 20;
  const holdLabel = scope === "ticker" ? "Holding the stock" : "Holding all tracked stocks";
  const skipped = data?.skipped_days ?? [];

  return (
    <div className="rounded-lg border border-sky-800/50 bg-sky-950/20 px-3 py-2 text-xs space-y-2">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="font-medium text-sky-300/90">
          Latest model (<span className="font-mono">{v}</span>) · daily read
          <span className="ml-2 font-normal text-slate-400">
            {days >= target ? `${days} days — 20-day results are now available` : `day ${days} of ${target}`}
          </span>
        </p>
        {data?.first_date && (
          <span className="text-[11px] text-slate-500">
            {data.first_date} → {data.last_date}
          </span>
        )}
      </div>

      {days === 0 ? (
        <p className="text-slate-500 leading-snug">
          No scored day yet under {v}. Each EOD run (8pm ET) scores the previous day&apos;s call against
          the next close, so this starts filling in after the next clean snapshot.
          {skipped.length > 0 && ` Skipped (no new prices): ${skipped.join(", ")}.`}
        </p>
      ) : (
        <>
          <div className="grid grid-cols-3 gap-2">
            {[
              { label: "Following the model", val: data?.model_cum_pct },
              { label: holdLabel, val: data?.hold_cum_pct },
              { label: "SPY", val: data?.spy_cum_pct },
            ].map((s) => (
              <div key={s.label} className="rounded border border-slate-700/60 bg-slate-900/40 px-2 py-1.5">
                <p className="text-[11px] text-slate-500">{s.label}</p>
                <p className={`font-mono tabular-nums text-sm ${tone(s.val)}`}>{pct(s.val)}</p>
              </div>
            ))}
          </div>
          <p className="text-slate-400">
            Model vs holding: <span className={`font-mono ${tone(data?.model_vs_hold_pct)}`}>{pct(data?.model_vs_hold_pct)}</span>
            {data?.model_vs_spy_pct != null && (
              <>
                {" · vs SPY: "}
                <span className={`font-mono ${tone(data.model_vs_spy_pct)}`}>{pct(data.model_vs_spy_pct)}</span>
              </>
            )}
            <span className="text-slate-600"> · reduced position on {data?.days_reduced ?? 0} of {days} days</span>
          </p>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[480px]">
              <thead>
                <tr className="text-left text-slate-500 border-b border-slate-700">
                  <th className="py-1 pr-2 font-medium">Call date → next</th>
                  <th className="py-1 pr-2 font-medium">Call</th>
                  <th className="py-1 pr-2 font-medium">Position</th>
                  <th className="py-1 pr-2 font-medium">Model</th>
                  <th className="py-1 pr-2 font-medium">Hold</th>
                  <th className="py-1 font-medium">SPY</th>
                </tr>
              </thead>
              <tbody>
                {(data?.rows ?? []).slice(0, maxRows).map((r) => (
                  <tr key={r.date} className="border-b border-slate-800 text-slate-300">
                    <td className="py-1 pr-2 font-mono whitespace-nowrap">
                      {r.date} → {r.next_date?.slice(5) ?? "—"}
                    </td>
                    <td className="py-1 pr-2">{scope === "all" ? `${r.tickers} stocks` : r.signal ?? "—"}</td>
                    <td className="py-1 pr-2 font-mono tabular-nums">{Math.round(r.exposure * 100)}%</td>
                    <td className={`py-1 pr-2 font-mono tabular-nums ${tone(r.model_return_pct)}`}>{pct(r.model_return_pct)}</td>
                    <td className={`py-1 pr-2 font-mono tabular-nums ${tone(r.hold_return_pct)}`}>{pct(r.hold_return_pct)}</td>
                    <td className={`py-1 font-mono tabular-nums ${tone(r.spy_return_pct)}`}>{pct(r.spy_return_pct)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
      <p className="text-[11px] text-slate-600 leading-snug">
        Early read, updated after every EOD run. One-day moves are mostly noise, so the 20-day result stays the
        main verdict. HOLD counts as a full position (same as holding), and TRIM/REDUCE as half, so the model
        only differs from holding on days it acts.
        {scope === "all" && " Equal-weighted across tracked stocks each day."}
        {days > 0 && skipped.length > 0 && ` Skipped (no new prices): ${skipped.join(", ")}.`}
      </p>
    </div>
  );
}
