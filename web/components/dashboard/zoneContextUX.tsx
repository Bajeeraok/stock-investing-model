"use client";

import { clsx } from "clsx";

export type CatchLevel = { id: string; label: string; price: number; role?: string };

export type ZoneContext = {
  zone_name?: string;
  state?: string;
  in_watch_zone?: boolean;
  in_bridge_band?: boolean;
  gap_low?: number | null;
  gap_high?: number | null;
  bridge_low?: number | null;
  bridge_high?: number | null;
  bridge_rationale?: string;
  catch_levels?: CatchLevel[];
  floor_tier_id?: string | null;
  ceiling_tier_id?: string | null;
  next_add_tier_id?: string | null;
};

const REGIME_GATE = 60;

export function pctFromPrice(currentPrice: number, levelPrice: number): string {
  if (!(currentPrice > 0)) return "—";
  const pct = ((levelPrice - currentPrice) / currentPrice) * 100;
  const sign = pct >= 0 ? "+" : "";
  return `${sign}${pct.toFixed(1)}%`;
}

export function CatchLevelsRow({
  levels,
  currentPrice,
  bridgeLow,
  bridgeHigh,
  bridgeRationale,
  sharedLabel,
  periodKey,
}: {
  levels?: CatchLevel[];
  currentPrice?: number | null;
  bridgeLow?: number | null;
  bridgeHigh?: number | null;
  bridgeRationale?: string;
  sharedLabel?: string;
  periodKey?: string;
}) {
  if (!levels?.length && bridgeLow == null) return null;

  const periodTone = periodKey
    ? periodKey.includes("today") || periodKey === "immediate"
      ? "border-cyan-500/35 bg-cyan-950/20"
      : periodKey.includes("days")
        ? "border-violet-500/35 bg-violet-950/20"
        : "border-emerald-500/35 bg-emerald-950/20"
    : "";

  return (
    <div
      className={clsx(
        "space-y-1.5",
        periodKey && "rounded-md border px-2 py-1.5",
        periodTone,
      )}
    >
      {sharedLabel && (
        <p className="text-[10px] uppercase tracking-wider text-slate-500">{sharedLabel}</p>
      )}
      {bridgeLow != null && bridgeHigh != null && (
        <div className="space-y-0.5">
          <p className="text-[10px] font-mono text-cyan-300/90">
            Bridge ${bridgeLow.toFixed(2)}–${bridgeHigh.toFixed(2)}
          </p>
          {bridgeRationale && (
            <p className="text-[10px] text-slate-400 leading-snug">{bridgeRationale}</p>
          )}
        </div>
      )}
      {levels && levels.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {levels.map((lv) => (
            <span
              key={lv.id}
              className={clsx(
                "inline-flex flex-col items-center rounded-md border px-2 py-0.5 text-[10px] font-mono tabular-nums",
                lv.role === "anchor"
                  ? "border-cyan-500/40 bg-cyan-950/40 text-cyan-200"
                  : "border-emerald-500/35 bg-emerald-950/30 text-emerald-200",
              )}
              title={lv.label}
            >
              <span>${lv.price.toFixed(2)}</span>
              {currentPrice != null && currentPrice > 0 && (
                <span className="text-[9px] text-slate-500">{pctFromPrice(currentPrice, lv.price)}</span>
              )}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

/** HMM bull progress toward 60% gate — loading-bar feel. */
export function RegimeGateProgress({
  bullPct,
  target = REGIME_GATE,
  label = "HMM Bull",
}: {
  bullPct: number | null | undefined;
  target?: number;
  label?: string;
}) {
  const pct = bullPct != null ? Math.max(0, Math.min(100, bullPct)) : null;
  if (pct == null) return null;

  const filled = Math.min(6, Math.max(0, Math.round((pct / target) * 6)));
  const dots = Array.from({ length: 6 }, (_, i) => i < filled);

  return (
    <div className="flex flex-wrap items-center gap-2 text-[10px]">
      <span className="text-slate-500 uppercase tracking-wider shrink-0">{label}</span>
      <span className="flex items-center gap-0.5" aria-hidden>
        {dots.map((on, i) => (
          <span
            key={i}
            className={clsx(
              "inline-block w-1.5 h-1.5 rounded-full",
              on ? "bg-emerald-400" : "bg-slate-600",
            )}
          />
        ))}
      </span>
      <span className="font-mono tabular-nums text-slate-300">
        {pct.toFixed(0)}% → need {target}%
      </span>
    </div>
  );
}

export function WatchZoneCallout({
  zone,
  currentPrice,
  regimeBullPct,
}: {
  zone: ZoneContext;
  currentPrice?: number | null;
  regimeBullPct?: number | null;
}) {
  const bridgeFmt =
    zone.bridge_low != null && zone.bridge_high != null
      ? `$${zone.bridge_low.toFixed(0)}–$${zone.bridge_high.toFixed(0)}`
      : null;

  return (
    <div className="rounded-xl border border-amber-500/30 bg-amber-950/20 px-3 py-2.5 space-y-2">
      <p className="text-sm font-semibold text-amber-100 flex items-center gap-2">
        <span className="inline-block w-2 h-2 rounded-full bg-amber-400 shrink-0" aria-hidden />
        Price in {zone.zone_name || "Watch Zone"}
        {bridgeFmt && zone.in_bridge_band ? (
          <span className="text-cyan-300 font-normal">· Bridge {bridgeFmt} active</span>
        ) : bridgeFmt ? (
          <span className="text-slate-400 font-normal text-xs">· Bridge {bridgeFmt} available</span>
        ) : null}
      </p>
      {regimeBullPct != null && regimeBullPct < REGIME_GATE && (
        <div className="rounded-lg border border-slate-700/60 bg-slate-900/40 px-2 py-1.5">
          <p className="text-[10px] text-slate-500 mb-1">Regime gate</p>
          <RegimeGateProgress bullPct={regimeBullPct} />
        </div>
      )}
      {zone.catch_levels && zone.catch_levels.length > 0 && (
        <CatchLevelsRow
          levels={zone.catch_levels}
          currentPrice={currentPrice}
          bridgeLow={zone.in_bridge_band ? zone.bridge_low : undefined}
          bridgeHigh={zone.in_bridge_band ? zone.bridge_high : undefined}
          bridgeRationale={zone.bridge_rationale}
        />
      )}
    </div>
  );
}

export function UnlockWhenStrip({ text }: { text: string | null | undefined }) {
  if (!text?.trim()) return null;
  return (
    <div className="sticky bottom-0 z-10 -mx-1 px-3 py-2.5 rounded-xl border border-emerald-500/35 bg-emerald-950/90 backdrop-blur-sm shadow-lg shadow-black/30">
      <p className="text-xs text-emerald-100 leading-snug">
        <span className="mr-1" aria-hidden>
          🔓
        </span>
        {text.replace(/^Unlocks when:\s*/i, "Unlocks when: ")}
      </p>
    </div>
  );
}

/** When ST says enter-now but LT core tier is lower — one clear reconcile line. */
export function HorizonReconcileStrip({
  text,
  mode = "swing",
}: {
  text: string | null | undefined;
  mode?: "scout" | "swing" | "owner";
}) {
  if (!text?.trim()) return null;
  const tone =
    mode === "owner"
      ? "border-violet-500/35 bg-violet-950/40 text-violet-100"
      : mode === "scout"
        ? "border-cyan-500/35 bg-cyan-950/35 text-cyan-100"
        : "border-amber-500/35 bg-amber-950/30 text-amber-100";
  return (
    <div className={clsx("rounded-xl border px-3 py-2.5", tone)} role="note">
      <p className="text-[10px] uppercase tracking-wider font-semibold opacity-80 mb-1">
        Two horizons — read together
      </p>
      <p className="text-xs leading-snug">{text}</p>
    </div>
  );
}
