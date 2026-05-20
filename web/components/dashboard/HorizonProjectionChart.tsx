"use client";

import { useMemo, useState } from "react";
import {
  ComposedChart,
  Line,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts";
import type { HorizonSignalPayload } from "./InvestorDecisionSummary";

export type PriceHistoryPoint = { date: string; close: number };

type HorizonKey = "short" | "medium" | "long";

const HORIZON_STYLE: Record<
  HorizonKey,
  { label: string; stroke: string; fill: string; daysDefault: number }
> = {
  short: { label: "Short", stroke: "#22d3ee", fill: "#22d3ee", daysDefault: 22 },
  medium: { label: "Medium", stroke: "#a78bfa", fill: "#a78bfa", daysDefault: 63 },
  long: { label: "Long", stroke: "#34d399", fill: "#34d399", daysDefault: 180 },
};

const HIST_DISPLAY_DAYS = 90;
const FORWARD_PAD_DAYS = 14;

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}

function parseHorizonDays(duration: string | undefined, kind: HorizonKey): number {
  const d = String(duration || "").toLowerCase();
  const week = d.match(/(\d+)\s*[- ]?\s*week/);
  if (week) return Math.min(365, Math.max(7, Number(week[1]) * 5));
  const month = d.match(/(\d+)\s*[- ]?\s*month/);
  if (month) return Math.min(365, Math.max(14, Number(month[1]) * 21));
  const day = d.match(/(\d+)\s*[- ]?\s*day/);
  if (day) return Math.min(365, Math.max(5, Number(day[1])));
  return HORIZON_STYLE[kind].daysDefault;
}

function chartStop(stop: number, current: number, kind: HorizonKey): number {
  if (!Number.isFinite(stop) || stop <= 0) return current * 0.94;
  if (kind === "long" && stop < current * 0.82) return current * 0.9;
  if (stop > current * 1.05) return current * 0.96;
  return stop;
}

function chartHigh(target: number, entryHigh: number, current: number): number {
  const candidates = [target, entryHigh, current].filter((n) => Number.isFinite(n) && n > 0);
  return Math.max(...candidates);
}

type ChartRow = {
  day: number;
  dateLabel?: string;
  price?: number | null;
  shortLow?: number;
  shortHigh?: number;
  shortMid?: number;
  mediumLow?: number;
  mediumHigh?: number;
  mediumMid?: number;
  longLow?: number;
  longHigh?: number;
  longMid?: number;
};

function buildChartRows(
  currentPrice: number,
  priceHistory: PriceHistoryPoint[],
  short?: HorizonSignalPayload | null,
  medium?: HorizonSignalPayload | null,
  long?: HorizonSignalPayload | null
): { rows: ChartRow[]; forwardMax: number; tickDays: number[] } {
  const hist = priceHistory.slice(-HIST_DISPLAY_DAYS);
  const histLen = hist.length;

  const horizons: {
    key: HorizonKey;
    h?: HorizonSignalPayload | null;
    days: number;
    target: number;
    stop: number;
    entryHigh: number;
  }[] = (
    [
      {
        key: "short" as const,
        h: short,
        days: parseHorizonDays(short?.duration, "short"),
        target: short?.target ?? currentPrice,
        stop: chartStop(short?.stop_loss ?? currentPrice * 0.95, currentPrice, "short"),
        entryHigh: short?.entry_zone?.high ?? short?.target ?? currentPrice,
      },
      {
        key: "medium" as const,
        h: medium,
        days: parseHorizonDays(medium?.duration, "medium"),
        target: medium?.target ?? currentPrice,
        stop: chartStop(medium?.stop_loss ?? currentPrice * 0.92, currentPrice, "medium"),
        entryHigh: medium?.entry_zone?.high ?? medium?.target ?? currentPrice,
      },
      {
        key: "long" as const,
        h: long,
        days: parseHorizonDays(long?.duration, "long"),
        target: long?.target ?? currentPrice,
        stop: chartStop(long?.stop_loss ?? currentPrice * 0.88, currentPrice, "long"),
        entryHigh: long?.entry_zone?.high ?? long?.target ?? currentPrice,
      },
    ] as const
  ).filter((x) => x.h && Number.isFinite(x.target) && x.target > 0);

  const forwardMax =
    horizons.length > 0
      ? Math.max(...horizons.map((h) => h.days)) + FORWARD_PAD_DAYS
      : 90;

  const rows: ChartRow[] = [];

  for (let i = 0; i < histLen; i++) {
    const day = i - histLen + 1;
    rows.push({
      day,
      dateLabel: hist[i]?.date,
      price: hist[i]?.close ?? null,
    });
  }

  for (let d = 0; d <= forwardMax; d++) {
    const row: ChartRow = {
      day: d,
      dateLabel: d === 0 ? "Today" : undefined,
      price: d === 0 ? currentPrice : null,
    };

    for (const hz of horizons) {
      const t = Math.min(1, d / hz.days);
      const mid = lerp(currentPrice, hz.target, t);
      const low = lerp(currentPrice, hz.stop, t);
      const high = lerp(currentPrice, chartHigh(hz.target, hz.entryHigh, currentPrice), t);
      if (hz.key === "short") {
        row.shortLow = low;
        row.shortHigh = high;
        row.shortMid = mid;
      } else if (hz.key === "medium") {
        row.mediumLow = low;
        row.mediumHigh = high;
        row.mediumMid = mid;
      } else {
        row.longLow = low;
        row.longHigh = high;
        row.longMid = mid;
      }
    }

    rows.push(row);
  }

  const tickDays = [
    -(histLen - 1),
    0,
    ...horizons.map((h) => h.days),
    forwardMax,
  ]
    .filter((v, i, arr) => arr.indexOf(v) === i)
    .sort((a, b) => a - b);

  return { rows, forwardMax, tickDays };
}

function fmtPrice(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return `$${n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function CustomTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: { payload?: ChartRow }[];
  label?: number;
}) {
  if (!active || !payload?.length) return null;
  const row = payload[0]?.payload;
  if (!row) return null;
  const day = typeof label === "number" ? label : row.day;

  return (
    <div className="rounded-lg border border-slate-600 bg-slate-900/95 px-3 py-2 text-xs shadow-xl max-w-[220px]">
      <p className="text-slate-400 mb-1">
        {day < 0 ? `${Math.abs(day)}d ago` : day === 0 ? "Today" : `+${day}d`}
        {row.dateLabel && day <= 0 ? ` · ${row.dateLabel}` : ""}
      </p>
      {row.price != null && (
        <p className="text-slate-100 font-medium">Price {fmtPrice(row.price)}</p>
      )}
      {(["short", "medium", "long"] as HorizonKey[]).map((k) => {
        const mid = row[`${k}Mid` as keyof ChartRow] as number | undefined;
        const low = row[`${k}Low` as keyof ChartRow] as number | undefined;
        const high = row[`${k}High` as keyof ChartRow] as number | undefined;
        if (mid == null) return null;
        return (
          <p key={k} style={{ color: HORIZON_STYLE[k].stroke }} className="mt-0.5">
            {HORIZON_STYLE[k].label}: {fmtPrice(low)} – {fmtPrice(high)} (avg {fmtPrice(mid)})
          </p>
        );
      })}
    </div>
  );
}

export function HorizonProjectionChart({
  ticker,
  currentPrice,
  priceHistory = [],
  short,
  medium,
  long,
  fairValue,
}: {
  ticker?: string;
  currentPrice: number;
  priceHistory?: PriceHistoryPoint[];
  short?: HorizonSignalPayload | null;
  medium?: HorizonSignalPayload | null;
  long?: HorizonSignalPayload | null;
  fairValue?: number | null;
}) {
  const [visible, setVisible] = useState<Record<HorizonKey, boolean>>({
    short: true,
    medium: true,
    long: true,
  });

  const { rows, tickDays } = useMemo(
    () => buildChartRows(currentPrice, priceHistory, short, medium, long),
    [currentPrice, priceHistory, short, medium, long]
  );

  const yDomain = useMemo(() => {
    let lo = currentPrice;
    let hi = currentPrice;
    for (const r of rows) {
      if (r.price != null) {
        lo = Math.min(lo, r.price);
        hi = Math.max(hi, r.price);
      }
      for (const k of ["short", "medium", "long"] as HorizonKey[]) {
        const low = r[`${k}Low` as keyof ChartRow] as number | undefined;
        const high = r[`${k}High` as keyof ChartRow] as number | undefined;
        if (low != null) lo = Math.min(lo, low);
        if (high != null) hi = Math.max(hi, high);
      }
    }
    if (fairValue != null && fairValue > 0) {
      lo = Math.min(lo, fairValue);
      hi = Math.max(hi, fairValue);
    }
    const pad = (hi - lo) * 0.08 || currentPrice * 0.05;
    return [lo - pad, hi + pad] as [number, number];
  }, [rows, currentPrice, fairValue]);

  const hasHistory = priceHistory.length >= 5;
  const hasHorizons = short?.target || medium?.target || long?.target;

  if (!hasHorizons || currentPrice <= 0) return null;

  const horizonMeta = (
    [
      { key: "short" as HorizonKey, h: short },
      { key: "medium" as HorizonKey, h: medium },
      { key: "long" as HorizonKey, h: long },
    ] as const
  ).filter((x) => x.h?.target);

  return (
    <div className="rounded-xl border border-slate-700/90 bg-slate-900/40 overflow-hidden">
      <div className="px-4 py-3 border-b border-slate-700/80 bg-slate-900/60">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <h3 className="text-sm font-semibold text-slate-200 tracking-tight">
              Price path &amp; target bands
              {ticker ? (
                <span className="text-slate-500 font-normal ml-1.5">· {ticker}</span>
              ) : null}
            </h3>
            <p className="text-[11px] text-slate-500 mt-1 leading-snug">
              Trailing price (left) → today → forward ST / MT / LT channels (high · avg · low).
              {!hasHistory ? " History limited — bands anchored at current price." : null}
            </p>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {horizonMeta.map(({ key, h }) => (
              <button
                key={key}
                type="button"
                onClick={() => setVisible((v) => ({ ...v, [key]: !v[key] }))}
                className={`text-[10px] px-2 py-1 rounded-full border transition-opacity ${
                  visible[key] ? "opacity-100" : "opacity-40"
                }`}
                style={{
                  borderColor: `${HORIZON_STYLE[key].stroke}55`,
                  backgroundColor: `${HORIZON_STYLE[key].fill}18`,
                  color: HORIZON_STYLE[key].stroke,
                }}
              >
                {HORIZON_STYLE[key].label} · {fmtPrice(h!.target)}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="p-3 sm:p-4">
        <div className="h-72 sm:h-80">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={rows} margin={{ top: 8, right: 12, left: 4, bottom: 4 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" vertical={false} />
              <XAxis
                dataKey="day"
                type="number"
                domain={["dataMin", "dataMax"]}
                ticks={tickDays}
                tick={{ fill: "#94a3b8", fontSize: 10 }}
                tickFormatter={(d: number) => {
                  if (d === 0) return "Today";
                  if (d < 0) return `${Math.abs(d)}d`;
                  return `+${d}d`;
                }}
              />
              <YAxis
                domain={yDomain}
                tick={{ fill: "#94a3b8", fontSize: 10 }}
                tickFormatter={(v: number) => `$${v.toFixed(0)}`}
                width={52}
              />
              <Tooltip content={<CustomTooltip />} />
              <ReferenceLine x={0} stroke="#fbbf24" strokeDasharray="4 4" label={{ value: "Now", fill: "#fbbf24", fontSize: 10, position: "insideTopRight" }} />

              {visible.long && (
                <>
                  <Area
                    type="monotone"
                    dataKey={["longLow", "longHigh"] as unknown as string}
                    stroke="none"
                    fill={HORIZON_STYLE.long.fill}
                    fillOpacity={0.12}
                    isAnimationActive={false}
                  />
                  <Line
                    type="monotone"
                    dataKey="longMid"
                    stroke={HORIZON_STYLE.long.stroke}
                    strokeWidth={1.5}
                    strokeDasharray="6 4"
                    dot={false}
                    isAnimationActive={false}
                  />
                </>
              )}
              {visible.medium && (
                <>
                  <Area
                    type="monotone"
                    dataKey={["mediumLow", "mediumHigh"] as unknown as string}
                    stroke="none"
                    fill={HORIZON_STYLE.medium.fill}
                    fillOpacity={0.16}
                    isAnimationActive={false}
                  />
                  <Line
                    type="monotone"
                    dataKey="mediumMid"
                    stroke={HORIZON_STYLE.medium.stroke}
                    strokeWidth={1.5}
                    strokeDasharray="4 3"
                    dot={false}
                    isAnimationActive={false}
                  />
                </>
              )}
              {visible.short && (
                <>
                  <Area
                    type="monotone"
                    dataKey={["shortLow", "shortHigh"] as unknown as string}
                    stroke="none"
                    fill={HORIZON_STYLE.short.fill}
                    fillOpacity={0.22}
                    isAnimationActive={false}
                  />
                  <Line
                    type="monotone"
                    dataKey="shortMid"
                    stroke={HORIZON_STYLE.short.stroke}
                    strokeWidth={2}
                    dot={false}
                    isAnimationActive={false}
                  />
                </>
              )}

              <Line
                type="monotone"
                dataKey="price"
                stroke="#f8fafc"
                strokeWidth={2.25}
                dot={false}
                connectNulls={false}
                isAnimationActive={false}
              />

              {fairValue != null && fairValue > 0 && (
                <ReferenceLine
                  y={fairValue}
                  stroke="#64748b"
                  strokeDasharray="2 6"
                  label={{ value: "Fair value", fill: "#94a3b8", fontSize: 10, position: "insideBottomRight" }}
                />
              )}
            </ComposedChart>
          </ResponsiveContainer>
        </div>

        <div className="mt-3 grid grid-cols-1 sm:grid-cols-3 gap-2 text-[10px]">
          {horizonMeta.map(({ key, h }) => (
            <div
              key={key}
              className="rounded-lg border border-slate-700/60 bg-slate-800/40 px-2.5 py-2"
              style={{ borderLeftColor: HORIZON_STYLE[key].stroke, borderLeftWidth: 3 }}
            >
              <p className="font-semibold" style={{ color: HORIZON_STYLE[key].stroke }}>
                {HORIZON_STYLE[key].label} · {h!.duration || `${parseHorizonDays(h!.duration, key)}d`}
              </p>
              <p className="text-slate-400 mt-0.5">
                Target {fmtPrice(h!.target)} · Stop {fmtPrice(h!.stop_loss)} · Entry {fmtPrice(h!.entry_zone?.low)}–{fmtPrice(h!.entry_zone?.high)}
              </p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
