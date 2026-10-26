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
  short: { label: "Short", stroke: "#22D3EE", fill: "#22D3EE", daysDefault: 22 },
  medium: { label: "Medium", stroke: "#A78BFA", fill: "#A78BFA", daysDefault: 63 },
  long: { label: "Long", stroke: "#00C896", fill: "#00C896", daysDefault: 180 },
};

const HIST_DISPLAY_DAYS = 90;
const FORWARD_PAD_DAYS = 14;

const FAIR_VALUE_STYLE = {
  label: "Model FV",
  stroke: "#00C896",
  fill: "#00C896",
};

function ChartLegendItem({
  color,
  label,
  dashed = false,
}: {
  color: string;
  label: string;
  dashed?: boolean;
}) {
  return (
    <span className="inline-flex items-center gap-1.5 text-[10px] text-td-muted">
      <span
        className="inline-block h-0 w-5 border-t-2"
        style={{
          borderColor: color,
          borderTopStyle: dashed ? "dashed" : "solid",
        }}
      />
      {label}
    </span>
  );
}

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

function addCalendarLabels(rows: ChartRow[], anchorDateStr: string): void {
  const anchor = new Date(`${anchorDateStr}T12:00:00`);
  if (Number.isNaN(anchor.getTime())) return;
  for (const row of rows) {
    const d = new Date(anchor);
    d.setDate(d.getDate() + row.day);
    row.calendarLabel = d.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "2-digit",
    });
    if (row.day === 0) row.dateLabel = "Today";
    else if (row.day > 0 && !row.dateLabel) row.dateLabel = row.calendarLabel;
  }
}

function avgTail(values: number[], period: number): number | null {
  if (values.length < period) return null;
  const tail = values.slice(-period);
  return tail.reduce((a, b) => a + b, 0) / tail.length;
}

function chartHigh(target: number, entryHigh: number, current: number): number {
  const candidates = [target, entryHigh, current].filter((n) => Number.isFinite(n) && n > 0);
  return Math.max(...candidates);
}

type ChartRow = {
  day: number;
  dateLabel?: string;
  calendarLabel?: string;
  price?: number | null;
  ma20?: number | null;
  ma50?: number | null;
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
    entryLow: number;
    entryHigh: number;
    pathStart: number;
    viable: boolean;
  }[] = (
    [
      {
        key: "short" as const,
        h: short,
        days: parseHorizonDays(short?.duration, "short"),
        target: short?.target ?? currentPrice,
        stop: chartStop(short?.stop_loss ?? currentPrice * 0.95, currentPrice, "short"),
        entryLow: short?.entry_zone?.low ?? currentPrice,
        entryHigh: short?.entry_zone?.high ?? short?.target ?? currentPrice,
        pathStart: 0,
        viable: short?.setup_viable !== false && short?.setup_status !== "no_setup",
      },
      {
        key: "medium" as const,
        h: medium,
        days: parseHorizonDays(medium?.duration, "medium"),
        target: medium?.target ?? currentPrice,
        stop: chartStop(medium?.stop_loss ?? currentPrice * 0.92, currentPrice, "medium"),
        entryLow: medium?.entry_zone?.low ?? currentPrice,
        entryHigh: medium?.entry_zone?.high ?? medium?.target ?? currentPrice,
        pathStart: 0,
        viable: medium?.setup_viable !== false && medium?.setup_status !== "no_setup",
      },
      {
        key: "long" as const,
        h: long,
        days: parseHorizonDays(long?.duration, "long"),
        target: long?.target ?? currentPrice,
        stop: chartStop(long?.stop_loss ?? currentPrice * 0.88, currentPrice, "long"),
        entryLow: long?.entry_zone?.low ?? currentPrice,
        entryHigh: long?.entry_zone?.high ?? long?.target ?? currentPrice,
        pathStart: 0,
        viable: long?.setup_viable !== false && long?.setup_status !== "no_setup",
      },
    ] as const
  )
    .map((x) => {
      // Pullback plans: project from entry mid → target/stop, not spot → crash/target.
      const mid = (Number(x.entryLow) + Number(x.entryHigh)) / 2;
      const isPullback =
        Number.isFinite(mid) &&
        mid > 0 &&
        mid < currentPrice * 0.995;
      return {
        ...x,
        pathStart: isPullback ? mid : currentPrice,
      };
    })
    .filter((x) => x.h && Number.isFinite(x.target) && x.target > 0 && x.viable);

  const forwardMax =
    horizons.length > 0
      ? Math.max(...horizons.map((h) => h.days)) + FORWARD_PAD_DAYS
      : 90;

  const rows: ChartRow[] = [];

  for (let i = 0; i < histLen; i++) {
    const day = i - histLen + 1;
    const closesSoFar = hist.slice(0, i + 1).map((p) => p.close);
    rows.push({
      day,
      dateLabel: hist[i]?.date,
      price: hist[i]?.close ?? null,
      ma20: avgTail(closesSoFar, 20),
      ma50: avgTail(closesSoFar, 50),
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
      const mid = lerp(hz.pathStart, hz.target, t);
      const low = lerp(hz.pathStart, hz.stop, t);
      const high = lerp(hz.pathStart, chartHigh(hz.target, hz.entryHigh, hz.pathStart), t);
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

  const anchorDate = hist[hist.length - 1]?.date ?? new Date().toISOString().slice(0, 10);
  addCalendarLabels(rows, anchorDate);

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
  fairValue,
}: {
  active?: boolean;
  payload?: { payload?: ChartRow }[];
  label?: number;
  fairValue?: number | null;
}) {
  if (!active || !payload?.length) return null;
  const row = payload[0]?.payload;
  if (!row) return null;
  const day = typeof label === "number" ? label : row.day;

  return (
    <div className="rounded-lg border border-td-line bg-td-surface/95 px-3 py-2 text-xs shadow-xl max-w-[220px]">
      <p className="text-td-muted mb-1">
        {day < 0 ? `${Math.abs(day)}d ago` : day === 0 ? "Today" : `+${day}d`}
        {row.dateLabel && day <= 0 ? ` · ${row.dateLabel}` : row.calendarLabel && day > 0 ? ` · ${row.calendarLabel}` : ""}
      </p>
      {row.price != null && (
        <p className="text-td-text font-medium">Price {fmtPrice(row.price)}</p>
      )}
      {fairValue != null && fairValue > 0 && (
        <p style={{ color: FAIR_VALUE_STYLE.stroke }} className="mt-0.5">
          {FAIR_VALUE_STYLE.label}: {fmtPrice(fairValue)}
        </p>
      )}
      {(["short", "medium", "long"] as HorizonKey[]).map((k) => {
        const mid = row[`${k}Mid` as keyof ChartRow] as number | undefined;
        const low = row[`${k}Low` as keyof ChartRow] as number | undefined;
        const high = row[`${k}High` as keyof ChartRow] as number | undefined;
        if (mid == null) return null;
        return (
          <p key={k} style={{ color: HORIZON_STYLE[k].stroke }} className="mt-0.5">
            {HORIZON_STYLE[k].label}: {fmtPrice(low)} – {fmtPrice(high)}
            {mid != null ? ` (target ${fmtPrice(mid)})` : ""}
          </p>
        );
      })}
    </div>
  );
}

function fmtPct(n: number): string {
  const sign = n >= 0 ? "+" : "";
  return `${sign}${n.toFixed(1)}%`;
}

/** Compact 90d price path — Phase E2 sparkline mode. */
function PriceSparkline({
  priceHistory,
  currentPrice,
  fairValue,
  targetPrice,
  onExpand,
}: {
  priceHistory: PriceHistoryPoint[];
  currentPrice: number;
  fairValue?: number | null;
  targetPrice?: number | null;
  onExpand?: () => void;
}) {
  const hist = priceHistory.slice(-60);
  const sparkData = useMemo(
    () => hist.map((p, i) => ({ i, close: p.close, date: p.date })),
    [hist]
  );

  const periodPct = useMemo(() => {
    if (hist.length < 2 || currentPrice <= 0) return null;
    const first = hist[0]?.close;
    if (!first || first <= 0) return null;
    return ((currentPrice - first) / first) * 100;
  }, [hist, currentPrice]);

  const sparkDomain = useMemo((): [number, number] => {
    const vals = hist.map((p) => p.close).filter((n) => n > 0);
    if (fairValue != null && fairValue > 0) vals.push(fairValue);
    if (targetPrice != null && targetPrice > 0) vals.push(targetPrice);
    if (vals.length === 0) return [currentPrice * 0.95, currentPrice * 1.05];
    const lo = Math.min(...vals);
    const hi = Math.max(...vals);
    const pad = (hi - lo) * 0.06 || currentPrice * 0.02;
    return [lo - pad, hi + pad];
  }, [hist, currentPrice, fairValue, targetPrice]);

  const trendUp = periodPct != null && periodPct >= 0;
  const stroke = trendUp ? "#00C896" : "#FF6B6B";

  if (sparkData.length < 3) {
    return (
      <div className="rounded-lg border border-td-line/60 bg-td-surface/40 px-3 py-2 text-xs text-td-muted">
        Price history too short for sparkline.
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-td-line/60 bg-td-surface/40 px-3 py-2">
      <div className="flex items-center justify-between gap-2 mb-1">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-[10px] uppercase tracking-wider text-td-muted shrink-0">90d path</span>
          {periodPct != null && (
            <span className={`text-xs font-mono tabular-nums ${trendUp ? "text-td-accent" : "text-td-crit"}`}>
              {fmtPct(periodPct)}
            </span>
          )}
          {fairValue != null && fairValue > 0 && currentPrice > 0 && (
            <span className="text-[10px] text-td-muted truncate hidden sm:inline">
              FV {fmtPrice(fairValue)}
            </span>
          )}
        </div>
        {onExpand && (
          <button
            type="button"
            onClick={onExpand}
            className="text-[10px] text-td-info/90 hover:text-td-info shrink-0"
          >
            Target bands →
          </button>
        )}
      </div>
      <div className="h-12 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={sparkData} margin={{ top: 2, right: 2, left: 2, bottom: 2 }}>
            <YAxis domain={sparkDomain} hide />
            <XAxis dataKey="i" hide />
            <Line
              type="monotone"
              dataKey="close"
              stroke={stroke}
              strokeWidth={1.75}
              dot={false}
              isAnimationActive={false}
            />
            {fairValue != null && fairValue > 0 && (
              <ReferenceLine y={fairValue} stroke="#00C896" strokeDasharray="2 3" strokeOpacity={0.55} />
            )}
            {targetPrice != null && targetPrice > 0 && targetPrice !== fairValue && (
              <ReferenceLine y={targetPrice} stroke="#22D3EE" strokeDasharray="2 3" strokeOpacity={0.45} />
            )}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
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
  ma20,
  ma50,
  variant = "full",
  planMode,
  chaseBanner,
  chaseDetail,
}: {
  ticker?: string;
  currentPrice: number;
  priceHistory?: PriceHistoryPoint[];
  short?: HorizonSignalPayload | null;
  medium?: HorizonSignalPayload | null;
  long?: HorizonSignalPayload | null;
  fairValue?: number | null;
  ma20?: number | null;
  ma50?: number | null;
  /** full = bands chart; sparkline = compact 90d path (Phase E2) */
  variant?: "full" | "sparkline";
  planMode?: string | null;
  chaseBanner?: string | null;
  chaseDetail?: string | null;
}) {
  const [expanded, setExpanded] = useState(variant === "full");
  const [visible, setVisible] = useState<Record<HorizonKey, boolean>>({
    short: true,
    medium: true,
    long: true,
  });
  const [showFairValue, setShowFairValue] = useState(true);

  const horizonMeta = (
    [
      { key: "short" as HorizonKey, h: short },
      { key: "medium" as HorizonKey, h: medium },
      { key: "long" as HorizonKey, h: long },
    ] as const
  ).filter((x) => x.h?.target);

  const horizonDaySet = useMemo(
    () => new Set(horizonMeta.map(({ h, key }) => parseHorizonDays(h!.duration, key))),
    [horizonMeta]
  );

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
  const primaryTarget = short?.target ?? medium?.target ?? long?.target ?? null;

  if (variant === "sparkline" && !expanded) {
    if (currentPrice <= 0 || priceHistory.length < 3) return null;
    return (
      <PriceSparkline
        priceHistory={priceHistory}
        currentPrice={currentPrice}
        fairValue={fairValue}
        targetPrice={primaryTarget}
        onExpand={hasHorizons ? () => setExpanded(true) : undefined}
      />
    );
  }

  if (!hasHorizons || currentPrice <= 0) return null;

  const showMa20 = ma20 != null && ma20 > 0;
  const showMa50 = ma50 != null && ma50 > 0;
  const hasFairValue = fairValue != null && fairValue > 0;
  const fairValueGapPct =
    hasFairValue && currentPrice > 0 ? ((fairValue - currentPrice) / currentPrice) * 100 : null;

  return (
    <div className="rounded-xl border border-td-line/90 bg-td-surface/40 overflow-hidden">
      <div className="px-4 py-3 border-b border-td-line/80 bg-td-surface/60">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <h3 className="text-sm font-semibold text-td-text tracking-tight">
              Price path &amp; target bands
              {ticker ? (
                <span className="text-td-muted font-normal ml-1.5">· {ticker}</span>
              ) : null}
            </h3>
            <p className="text-sm text-td-muted mt-1 leading-snug">
              Trailing price (left) → today → forward ST / MT / LT channels.
              Pullback plans project from the entry band (not a crash-from-spot path).
              {hasFairValue ? " Emerald dashed line = model fair value." : null}
              {!hasHistory ? " History limited — bands anchored at current price." : null}
            </p>
          </div>
          <div className="flex flex-wrap gap-1.5 items-center">
            {variant === "sparkline" && expanded && (
              <button
                type="button"
                onClick={() => setExpanded(false)}
                className="text-xs px-2 py-1 rounded-full border border-td-line text-td-muted hover:text-td-text"
              >
                Collapse
              </button>
            )}
            {hasFairValue && (
              <button
                type="button"
                onClick={() => setShowFairValue((v) => !v)}
                className={`text-xs px-2 py-1 rounded-full border transition-opacity ${
                  showFairValue ? "opacity-100" : "opacity-40"
                }`}
                style={{
                  borderColor: `${FAIR_VALUE_STYLE.stroke}55`,
                  backgroundColor: `${FAIR_VALUE_STYLE.fill}18`,
                  color: FAIR_VALUE_STYLE.stroke,
                }}
              >
                {FAIR_VALUE_STYLE.label} · {fmtPrice(fairValue)}
              </button>
            )}
            {horizonMeta.map(({ key, h }) => (
              <button
                key={key}
                type="button"
                onClick={() => setVisible((v) => ({ ...v, [key]: !v[key] }))}
                className={`text-xs px-2 py-1 rounded-full border transition-opacity ${
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
        {(chaseBanner || planMode === "pullback_conditional") && (
          <div className="mb-3 rounded-lg border border-td-crit/40 bg-td-crit-weak/30 px-3 py-2">
            <p className="text-xs font-semibold uppercase tracking-wide text-td-crit">
              {chaseBanner || "ABOVE FAIR VALUE"}
            </p>
            <p className="text-[11px] text-td-crit/80 mt-0.5 leading-snug">
              {chaseDetail ||
                "Spot is above model FV — forward channels start from the entry band as optional cheaper-fill plans, not a forecast of a drop from today's print."}
            </p>
          </div>
        )}
        <div className="h-72 sm:h-80">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={rows} margin={{ top: 8, right: 12, left: 4, bottom: 4 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#262f42" vertical={false} />
              <XAxis
                dataKey="day"
                type="number"
                domain={["dataMin", "dataMax"]}
                ticks={tickDays}
                tick={{ fill: "#8690a6", fontSize: 10 }}
                tickFormatter={(d: number) => {
                  const row = rows.find((r) => r.day === d);
                  if (d === 0) return row?.calendarLabel ? `Today` : "Today";
                  if (row?.calendarLabel && (d === tickDays[0] || d === tickDays[tickDays.length - 1] || horizonDaySet.has(d))) {
                    return row.calendarLabel;
                  }
                  if (d < 0) return `${Math.abs(d)}d`;
                  return `+${d}d`;
                }}
              />
              <YAxis
                domain={yDomain}
                tick={{ fill: "#8690a6", fontSize: 10 }}
                tickFormatter={(v: number) => `$${v.toFixed(0)}`}
                width={52}
              />
              <Tooltip
                content={(props) => (
                  <CustomTooltip {...props} fairValue={showFairValue ? fairValue : null} />
                )}
              />
              <ReferenceLine x={0} stroke="#F59E0B" strokeWidth={2} label={{ value: "Now", fill: "#F59E0B", fontSize: 11, position: "insideTopRight" }} />

              {(showMa20 || rows.some((r) => r.ma20 != null)) && (
                <Line
                  type="monotone"
                  dataKey="ma20"
                  stroke="#F59E0B"
                  strokeWidth={1}
                  strokeDasharray="3 3"
                  dot={false}
                  connectNulls={false}
                  isAnimationActive={false}
                />
              )}
              {(showMa50 || rows.some((r) => r.ma50 != null)) && (
                <Line
                  type="monotone"
                  dataKey="ma50"
                  stroke="#8690a6"
                  strokeWidth={1}
                  strokeDasharray="5 2"
                  dot={false}
                  connectNulls={false}
                  isAnimationActive={false}
                />
              )}

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
                stroke="#e8ebf2"
                strokeWidth={2.25}
                dot={false}
                connectNulls={false}
                isAnimationActive={false}
              />

              {hasFairValue && showFairValue && (
                <ReferenceLine
                  y={fairValue}
                  stroke={FAIR_VALUE_STYLE.stroke}
                  strokeWidth={1.75}
                  strokeDasharray="6 4"
                  label={{
                    value: `${FAIR_VALUE_STYLE.label} ${fmtPrice(fairValue)}`,
                    fill: FAIR_VALUE_STYLE.stroke,
                    fontSize: 10,
                    position: "insideTopLeft",
                  }}
                />
              )}
            </ComposedChart>
          </ResponsiveContainer>
        </div>

        <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1">
          <ChartLegendItem color="#e8ebf2" label="Historical price" />
          {hasFairValue && showFairValue && (
            <ChartLegendItem
              color={FAIR_VALUE_STYLE.stroke}
              label={`${FAIR_VALUE_STYLE.label} ${fmtPrice(fairValue)}`}
              dashed
            />
          )}
          {(showMa20 || rows.some((r) => r.ma20 != null)) && (
            <ChartLegendItem color="#F59E0B" label="MA20" dashed />
          )}
          {(showMa50 || rows.some((r) => r.ma50 != null)) && (
            <ChartLegendItem color="#8690a6" label="MA50" dashed />
          )}
          {visible.short && short?.target && short?.setup_status !== "no_setup" && (
            <ChartLegendItem color={HORIZON_STYLE.short.stroke} label="Short projection" />
          )}
          {visible.medium && medium?.target && medium?.setup_status !== "no_setup" && (
            <ChartLegendItem color={HORIZON_STYLE.medium.stroke} label="Medium projection" />
          )}
          {visible.long && long?.target && long?.setup_status !== "no_setup" && (
            <ChartLegendItem color={HORIZON_STYLE.long.stroke} label="Long projection" />
          )}
        </div>

        <div
          className={`mt-3 grid grid-cols-1 gap-2 text-xs ${
            hasFairValue && showFairValue
              ? "sm:grid-cols-2 lg:grid-cols-4"
              : "sm:grid-cols-3"
          }`}
        >
          {hasFairValue && showFairValue && (
            <div
              className="rounded-lg border border-td-line/60 bg-td-surface2/40 px-2.5 py-2"
              style={{ borderLeftColor: FAIR_VALUE_STYLE.stroke, borderLeftWidth: 3 }}
            >
              <p className="font-semibold" style={{ color: FAIR_VALUE_STYLE.stroke }}>
                {FAIR_VALUE_STYLE.label} · fundamentals anchor
              </p>
              <p className="text-td-muted mt-0.5">
                Fair value {fmtPrice(fairValue)}
                {fairValueGapPct != null
                  ? ` · ${fairValueGapPct >= 0 ? "+" : ""}${fairValueGapPct.toFixed(1)}% vs now`
                  : null}
              </p>
            </div>
          )}
          {horizonMeta.map(({ key, h }) => {
            const noSetup = h!.setup_status === "no_setup" || h!.setup_viable === false;
            const touch = h!.entry_touch_forecast?.touch_probability_pct;
            return (
            <div
              key={key}
              className="rounded-lg border border-td-line/60 bg-td-surface2/40 px-2.5 py-2"
              style={{ borderLeftColor: HORIZON_STYLE[key].stroke, borderLeftWidth: 3 }}
            >
              <p className="font-semibold" style={{ color: HORIZON_STYLE[key].stroke }}>
                {HORIZON_STYLE[key].label} · {h!.duration || `${parseHorizonDays(h!.duration, key)}d`}
                {noSetup ? " · no setup" : ""}
              </p>
              {noSetup ? (
                <p className="text-td-muted mt-0.5">
                  No setup at this horizon — edge or R:R from entry fails the quality gate.
                </p>
              ) : (
                <p className="text-td-muted mt-0.5">
                  Target {fmtPrice(h!.target)} · Stop {fmtPrice(h!.stop_loss)} · Entry {fmtPrice(h!.entry_zone?.low)}–{fmtPrice(h!.entry_zone?.high)}
                  {touch != null ? ` · Touch ~${Number(touch).toFixed(0)}%` : ""}
                </p>
              )}
            </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
