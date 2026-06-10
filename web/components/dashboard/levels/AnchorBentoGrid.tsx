"use client";

import { clsx } from "clsx";

export interface AnchorCard {
  id: string;
  label: string;
  value: number | null;
  /** % distance from current price — positive = above, negative = below */
  distPct: number | null;
  color: "emerald" | "amber" | "orange" | "red" | "slate" | "cyan" | "violet" | "white";
  role?: "support" | "resistance" | "current" | "target";
  sublabel?: string;
}

const BORDER: Record<AnchorCard["color"], string> = {
  emerald: "border-emerald-500/30 bg-emerald-950/20",
  amber:   "border-amber-500/30 bg-amber-950/20",
  orange:  "border-orange-500/30 bg-orange-950/20",
  red:     "border-red-500/30 bg-red-950/20",
  slate:   "border-slate-700/40 bg-slate-900/40",
  cyan:    "border-cyan-500/30 bg-cyan-950/20",
  violet:  "border-violet-500/30 bg-violet-950/20",
  white:   "border-slate-500/50 bg-slate-800/60",
};

const TEXT: Record<AnchorCard["color"], string> = {
  emerald: "text-emerald-300",
  amber:   "text-amber-300",
  orange:  "text-orange-300",
  red:     "text-red-300",
  slate:   "text-slate-400",
  cyan:    "text-cyan-300",
  violet:  "text-violet-300",
  white:   "text-white",
};

const DOT: Record<AnchorCard["color"], string> = {
  emerald: "bg-emerald-400",
  amber:   "bg-amber-400",
  orange:  "bg-orange-400",
  red:     "bg-red-400",
  slate:   "bg-slate-500",
  cyan:    "bg-cyan-400",
  violet:  "bg-violet-400",
  white:   "bg-white",
};

function fmt(v: number | null): string {
  if (v == null) return "—";
  return "$" + v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function fmtPct(v: number | null): string {
  if (v == null) return "";
  const abs = Math.abs(v);
  const sign = v >= 0 ? "+" : "−";
  return `${sign}${abs.toFixed(1)}%`;
}

export function AnchorBentoGrid({
  anchors,
  className,
}: {
  anchors: AnchorCard[];
  className?: string;
}) {
  return (
    <div className={clsx("grid grid-cols-2 sm:grid-cols-3 gap-2", className)}>
      {anchors.map((a) => (
        <div
          key={a.id}
          className={clsx(
            "rounded-xl border backdrop-blur-sm p-3 flex flex-col gap-1",
            BORDER[a.color],
            a.role === "current" && "sm:col-span-1 ring-1 ring-white/10",
          )}
        >
          <div className="flex items-center gap-1.5">
            <span className={clsx("w-1.5 h-1.5 rounded-full shrink-0", DOT[a.color])} />
            <span className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold">{a.label}</span>
          </div>
          <span className={clsx("text-base font-mono font-bold tabular-nums", TEXT[a.color])}>
            {fmt(a.value)}
          </span>
          {(a.distPct != null || a.sublabel) && (
            <div className="flex items-center justify-between gap-1 mt-0.5">
              {a.distPct != null && (
                <span
                  className={clsx(
                    "text-[10px] font-mono tabular-nums",
                    a.distPct > 0 ? "text-emerald-400/70" : a.distPct < 0 ? "text-red-400/70" : "text-slate-500",
                  )}
                >
                  {fmtPct(a.distPct)} to current
                </span>
              )}
              {a.sublabel && !a.distPct && (
                <span className="text-[10px] text-slate-500">{a.sublabel}</span>
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

/** Build anchors from the `technical_levels` API payload. */
export function anchorsFromTechnicalLevels(
  lv: { ma50?: number | null; ma200?: number | null; low_52w?: number | null; high_52w?: number | null },
  currentPrice: number,
): AnchorCard[] {
  const dist = (v: number | null) => (v != null && currentPrice > 0 ? ((currentPrice - v) / v) * 100 : null);
  const items: AnchorCard[] = [];
  if (lv.low_52w != null) items.push({ id: "52w_low", label: "52w Low", value: lv.low_52w, distPct: dist(lv.low_52w), color: "red", role: "support", sublabel: "annual floor" });
  if (lv.ma200 != null) items.push({ id: "ma200", label: "MA200", value: lv.ma200, distPct: dist(lv.ma200), color: "orange", role: "support", sublabel: "long-term avg" });
  if (lv.ma50 != null) items.push({ id: "ma50", label: "MA50", value: lv.ma50, distPct: dist(lv.ma50), color: "amber", role: "support", sublabel: "swing avg" });
  items.push({ id: "current", label: "Current", value: currentPrice, distPct: 0, color: "white", role: "current", sublabel: "live price" });
  if (lv.high_52w != null) items.push({ id: "52w_high", label: "52w High", value: lv.high_52w, distPct: dist(lv.high_52w), color: "emerald", role: "resistance", sublabel: "annual peak" });
  return items;
}
