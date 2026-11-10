"use client";

import type { LossScorecard, TrackRecordResponse } from "@/lib/useTickerTrackRecord";
import { fmtPct } from "./ReferenceDetailGrid";

const BUY_PILL: Record<string, { label: string; cls: string }> = {
  ok: { label: "Losses small, gains bigger", cls: "bg-emerald-500/15 text-emerald-300" },
  weak: { label: "Losses bigger than gains", cls: "bg-amber-500/15 text-amber-300" },
  losing: { label: "Buys losing money", cls: "bg-red-500/15 text-red-300" },
  too_few: { label: "Too few buys to judge", cls: "bg-slate-500/15 text-slate-400" },
};

const EXIT_PILL: Record<string, { label: string; cls: string }> = {
  ok: { label: "Saved more than it missed", cls: "bg-emerald-500/15 text-emerald-300" },
  costing: { label: "Missed more than it saved", cls: "bg-red-500/15 text-red-300" },
  too_few: { label: "Too few to judge", cls: "bg-slate-500/15 text-slate-400" },
};

function pick(sc: { current?: LossScorecard | null; all?: LossScorecard | null } | undefined) {
  const cur = sc?.current;
  const enough = (c?: LossScorecard | null) =>
    !!c && ((c.buys?.n ?? 0) >= c.min_n || (c.exits?.n ?? 0) >= c.min_n);
  if (enough(cur)) return { card: cur!, scope: "current model" };
  if (sc?.all) return { card: sc.all, scope: "all model versions" };
  return cur ? { card: cur, scope: "current model" } : null;
}

function Pill({ map, status }: { map: Record<string, { label: string; cls: string }>; status?: string }) {
  const p = status ? map[status] : undefined;
  return p ? <span className={`rounded-full px-2 py-0.5 text-[12px] ${p.cls}`}>{p.label}</span> : null;
}

/** Core principle check: losses small and rare, gains bigger (docs/signals/SIGNAL_RULES.md). */
export default function LossScorecardCard({ data }: { data: TrackRecordResponse }) {
  const sc = data.loss_scorecard;
  if (!sc) return null;
  const rows = ["20", "5"].map((h) => ({ h, sel: pick(sc[h] ?? undefined) })).filter((r) => r.sel);
  if (rows.length === 0) return null;
  return (
    <div className="rounded-lg border border-td-line p-3 space-y-2">
      <p className="text-[13px] font-semibold text-slate-200">Loss check — losses small and rare, gains bigger</p>
      {rows.map(({ h, sel }) => {
        const { card, scope } = sel!;
        const b = card.buys;
        const e = card.exits;
        return (
          <div key={h} className="space-y-1 text-[13px] text-slate-300">
            <p className="text-slate-400">
              {h}-day result · {scope}
            </p>
            {b && (
              <p className="flex flex-wrap items-center gap-2">
                <span>
                  <span className="text-slate-400">Buy calls ({b.n}):</span> avg{" "}
                  <span className={(b.avg_pnl_pct ?? 0) >= 0 ? "text-emerald-400" : "text-red-400"}>
                    {fmtPct(b.avg_pnl_pct)}
                  </span>{" "}
                  · lost on {b.loss_rate_pct.toFixed(0)}% · avg loss {fmtPct(b.avg_loss_pct)} vs avg gain{" "}
                  {fmtPct(b.avg_gain_pct)} · worst {fmtPct(b.worst_loss_pct)}
                </span>
                <Pill map={BUY_PILL} status={card.buys_status} />
              </p>
            )}
            {e && (
              <p className="flex flex-wrap items-center gap-2">
                <span>
                  <span className="text-slate-400">Trim/avoid calls ({e.n}):</span> avoided a drop {e.losses_avoided_n}× (avg{" "}
                  {fmtPct(e.avg_drop_avoided_pct)}) · missed a gain {e.missed_gain_n}× (avg {fmtPct(e.avg_missed_gain_pct)})
                </span>
                <Pill map={EXIT_PILL} status={card.exits_status} />
              </p>
            )}
          </div>
        );
      })}
      <p className="text-[12px] text-slate-600 leading-snug">
        Each EOD buy or trim/avoid call on this ticker, scored by the price change over the next 5 or 20 trading days.
        HOLD isn&apos;t scored. Calls on back-to-back days overlap, so treat fewer than {rows[0].sel!.card.min_n} calls as
        noise.
      </p>
    </div>
  );
}
