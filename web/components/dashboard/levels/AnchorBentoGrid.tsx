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
  emerald: "border-td-accent/30 bg-td-accent-weak/20",
  amber:   "border-td-warn/30 bg-td-warn-weak/20",
  orange:  "border-td-warn/30 bg-td-warn-weak/20",
  red:     "border-td-crit/30 bg-td-crit-weak/20",
  slate:   "border-td-line/40 bg-td-surface/40",
  cyan:    "border-td-info/30 bg-td-info/10/20",
  violet:  "border-td-owner/30 bg-td-owner-weak/20",
  white:   "border-td-line/50 bg-td-surface2/60",
};

const TEXT: Record<AnchorCard["color"], string> = {
  emerald: "text-td-accent",
  amber:   "text-td-warn",
  orange:  "text-td-warn",
  red:     "text-td-crit",
  slate:   "text-td-muted",
  cyan:    "text-td-info",
  violet:  "text-td-owner",
  white:   "text-td-text",
};

const DOT: Record<AnchorCard["color"], string> = {
  emerald: "bg-td-accent",
  amber:   "bg-td-warn",
  orange:  "bg-td-warn",
  red:     "bg-td-crit",
  slate:   "bg-td-line",
  cyan:    "bg-td-info",
  violet:  "bg-td-owner",
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
    <div className={clsx(
      "flex items-center gap-x-3 gap-y-1 flex-wrap",
      className,
    )}>
      {anchors.map((a, i) => (
        <div key={a.id} className="flex items-center gap-1.5 min-w-0">
          {/* Separator between items */}
          {i > 0 && (
            <span className="text-td-muted text-[10px] select-none mr-1">·</span>
          )}
          <span className={clsx("w-1.5 h-1.5 rounded-full shrink-0", DOT[a.color])} />
          <span className="text-[10px] text-td-muted uppercase tracking-wide font-medium shrink-0">
            {a.label}
          </span>
          <span className={clsx("text-[11px] font-mono font-semibold tabular-nums", TEXT[a.color])}>
            {fmt(a.value)}
          </span>
          {a.distPct != null && a.role !== "current" && (
            <span className={clsx(
              "text-[9px] font-mono tabular-nums",
              a.distPct > 0 ? "text-td-accent/60" : "text-td-crit/60",
            )}>
              {fmtPct(a.distPct)}
            </span>
          )}
          {a.role === "current" && (
            <span className="text-[9px] text-td-muted italic">live</span>
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
