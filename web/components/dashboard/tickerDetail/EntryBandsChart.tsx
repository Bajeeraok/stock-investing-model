"use client";

/**
 * Levels tab — chart-first entry band overlay.
 * Paints ST/MT/LT entry zones as shaded horizontal bands plus spot, stop,
 * and target lines — TradingView position-tool style. Price axis is shared
 * so zones read against each other; no OHLCV needed.
 *
 * Domain is clamped to levels within ±50% of spot: far-away anchors (deep LT
 * tiers, 2x targets) used to stretch the axis until the actionable bands were
 * unreadable — they now pin to the nearest chart edge as tags instead.
 */
import React from "react";
import clsx from "clsx";

type Band = { label: string; low?: number | null; high?: number | null; kind: "entry" | "tier" | "stop" | "target" | "fv" | "ma" };
type Props = {
  currentPrice?: number | null;
  bands: Band[];
  className?: string;
};

const KIND_STYLE: Record<Band["kind"], { fill: string; stroke: string; text: string }> = {
  entry: { fill: "rgba(16,185,129,0.18)", stroke: "#10B981", text: "text-emerald-300" },
  tier: { fill: "rgba(52,211,153,0.10)", stroke: "#34D399", text: "text-emerald-400/80" },
  stop: { fill: "rgba(244,63,94,0.15)", stroke: "#F43F5E", text: "text-rose-300" },
  target: { fill: "rgba(34,211,238,0.12)", stroke: "#22D3EE", text: "text-cyan-300" },
  fv: { fill: "rgba(168,85,247,0.10)", stroke: "#A855F7", text: "text-purple-300" },
  ma: { fill: "rgba(129,140,248,0.10)", stroke: "#818CF8", text: "text-indigo-300" },
};

const EDGE_SPAN = 0.5;   // a level within ±50% of spot stays on-axis; beyond → edge tag
const LABEL_GAP = 7;     // min vertical gap between right-edge labels (% of chart height)

function bandPriceText(b: Band): string {
  return b.low != null && b.high != null && b.high !== b.low
    ? `$${b.low.toFixed(0)}–$${b.high.toFixed(0)}`
    : `$${(b.low ?? b.high)!.toFixed(0)}`;
}

export function EntryBandsChart({ currentPrice, bands, className }: Props) {
  const spot = currentPrice != null && currentPrice > 0 ? currentPrice : null;

  // Dedupe identical zones (e.g. "T1 MA200" entry_zone == tier t1 band).
  const seen = new Set<string>();
  const deduped = bands.filter((b) => {
    const key = `${b.kind}:${b.low?.toFixed(2)}:${b.high?.toFixed(2)}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });

  // Domain: spot + every band edge within ±EDGE_SPAN of spot.
  const coreVals: number[] = [];
  if (spot != null) coreVals.push(spot);
  for (const b of deduped) {
    for (const v of [b.low, b.high]) {
      if (v == null || v <= 0) continue;
      if (spot == null || (v >= spot * (1 - EDGE_SPAN) && v <= spot * (1 + EDGE_SPAN))) coreVals.push(v);
    }
  }
  if (coreVals.length === 0) return null;

  let lo = Math.min(...coreVals), hi = Math.max(...coreVals);
  const pad = (hi - lo) * 0.12 || hi * 0.05;
  lo -= pad; hi += pad;
  const range = hi - lo;
  const y = (p: number) => 100 - ((p - lo) / range) * 100; // svg % (0 = top)

  // Partition: in-window bands paint to scale; outside bands pin to an edge tag.
  const inWin: Band[] = [];
  const pinnedAbove: Band[] = [];
  const pinnedBelow: Band[] = [];
  for (const b of deduped) {
    const edges = [b.low, b.high].filter((v): v is number => v != null && v > 0);
    if (!edges.length) continue;
    const mid = (Math.min(...edges) + Math.max(...edges)) / 2;
    if (spot != null && mid > hi) pinnedAbove.push(b);
    else if (spot != null && mid < lo) pinnedBelow.push(b);
    else inWin.push(b);
  }
  pinnedAbove.sort((a, b) => (a.low ?? a.high ?? 0) - (b.low ?? b.high ?? 0));
  pinnedBelow.sort((a, b) => (b.low ?? b.high ?? 0) - (a.low ?? a.high ?? 0));

  // Right-edge labels: desired y = top of band (or line), then enforce min gap.
  const labels = inWin.map((b) => ({
    b,
    top: b.high != null ? y(b.high) : y(b.low ?? 0),
  }));
  labels.sort((a, b) => a.top - b.top);
  let cursor = 1;
  for (const l of labels) {
    l.top = Math.max(l.top, cursor);
    cursor = l.top + LABEL_GAP;
  }
  const overflow = (labels.length ? labels[labels.length - 1].top : 0) - 96;
  if (overflow > 0) for (const l of labels) l.top -= overflow;

  return (
    <div className={clsx("rounded-xl border border-td-line bg-td-surface/60 p-3", className)}>
      <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-td-muted mb-2">
        Entry levels vs spot
      </p>
      <div className="relative w-full" style={{ aspectRatio: "3 / 2" }}>
        <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="absolute inset-0 h-full w-full">
          {inWin.map((b, i) => {
            const s = KIND_STYLE[b.kind];
            if (b.low != null && b.high != null && b.high > b.low) {
              return (
                <rect key={i} x={8} width={80} y={y(b.high)} height={y(b.low) - y(b.high)}
                  fill={s.fill} stroke={s.stroke} strokeWidth={0.25} rx={0.4} />
              );
            }
            const p = b.low ?? b.high;
            if (p == null) return null;
            return <line key={i} x1={8} x2={88} y1={y(p)} y2={y(p)} stroke={s.stroke}
              strokeWidth={0.4} strokeDasharray={b.kind === "stop" ? "1.5 1" : b.kind === "ma" ? "0.5 1.5" : "2.5 1.5"} />;
          })}
          {spot != null && (
            <line x1={4} x2={96} y1={y(spot)} y2={y(spot)}
              stroke="#F59E0B" strokeWidth={0.7} />
          )}
        </svg>

        {/* Pinned out-of-window levels — edge tags, not scale stretchers */}
        {pinnedAbove.map((b, i) => (
          <span key={`a${i}`}
            className={clsx("absolute right-1 text-[9px] font-mono leading-none opacity-80", KIND_STYLE[b.kind].text)}
            style={{ top: `${1 + i * 5}%` }}>
            ▲ {b.label} {bandPriceText(b)}
          </span>
        ))}
        {pinnedBelow.map((b, i) => (
          <span key={`b${i}`}
            className={clsx("absolute right-1 text-[9px] font-mono leading-none opacity-80", KIND_STYLE[b.kind].text)}
            style={{ bottom: `${1 + i * 5}%` }}>
            ▼ {b.label} {bandPriceText(b)}
          </span>
        ))}

        {/* Labels — HTML overlay, gap-resolved */}
        {labels.map(({ b, top }, i) => {
          const s = KIND_STYLE[b.kind];
          return (
            <span key={i}
              className={clsx("absolute right-1 text-[10px] font-mono leading-none", s.text)}
              style={{ top: `${top}%`, transform: "translateY(-50%)" }}>
              {b.label} {bandPriceText(b)}
            </span>
          );
        })}
        {spot != null && (
          <span className="absolute left-1 text-[10px] font-mono font-bold leading-none text-amber-300"
            style={{ top: `${y(spot)}%`, transform: "translateY(-110%)" }}>
            SPOT ${spot.toFixed(2)}
          </span>
        )}
      </div>
    </div>
  );
}

/** Build bands[] from a horizons payload (short/medium/long entry zones + stops/targets + FV).
 * `technicalLevels` (optional, priceTargets.technical_levels) adds MA50/MA200 markers. */
export function bandsFromHorizons(horizons: any, currentPrice?: number | null, technicalLevels?: { ma50?: number | null; ma200?: number | null } | null): Band[] {
  const out: Band[] = [];
  const H = horizons || {};
  const push = (label: string, ez: any, kind: Band["kind"]) => {
    const lo = ez?.low ?? ez?.[0], hi = ez?.high ?? ez?.[1];
    if (lo != null || hi != null) out.push({ label, low: lo, high: hi ?? lo, kind });
  };
  push("ST zone", H.short?.entry_zone, "entry");
  push("MT zone", H.medium?.entry_zone, "entry");
  const lt = H.long || {};
  push("T1 MA200", lt.entry_zone, "tier");
  for (const t of lt.entry_tiers?.tiers || []) {
    push(t.id || "tier", { low: t.low, high: t.high }, t.id === "T2" ? "entry" : "tier");
  }
  for (const [k, h] of [["ST stop", H.short], ["MT stop", H.medium]] as const) {
    if (h?.stop_loss) out.push({ label: k, low: h.stop_loss, high: null, kind: "stop" });
  }
  for (const [k, h] of [["ST tgt", H.short], ["MT tgt", H.medium], ["LT tgt", H.long]] as const) {
    if (h?.target) out.push({ label: k, low: h.target, high: null, kind: "target" });
  }
  const fv = H.long?.fair_value ?? H.fair_value;
  if (fv) out.push({ label: "FV", low: fv, high: null, kind: "fv" });
  if (technicalLevels?.ma50 != null) out.push({ label: "MA50", low: technicalLevels.ma50, high: null, kind: "ma" });
  if (technicalLevels?.ma200 != null) out.push({ label: "MA200", low: technicalLevels.ma200, high: null, kind: "ma" });
  return out;
}
