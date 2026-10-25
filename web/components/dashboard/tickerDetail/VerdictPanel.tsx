"use client";

/**
 * Verdict tab — the redesign's "plain sentence before any number" layout:
 *   1. Verdict card: action label, one plain sentence, why-in-one-line, how long it has held
 *   2. Unlocks when: blocked gates first (what would flip it), passing gates after
 *   3. Risk:Reward + Next catalyst tiles
 *   4. Historical hit rate for this ticker (same track-record response as the Track tab)
 *   5. Action bar: Alert me at $X · Notes (journal) · Copy plan
 *
 * Everything reads the same investor_summary horizon + gate rows the Why and Levels tabs
 * use (passed in from TickerDetailModal), so the three tabs can't disagree.
 */

import { useEffect, useState, type ReactNode } from "react";
import { clsx } from "clsx";
import { Bell, BellOff, ChevronRight, NotebookPen } from "lucide-react";
import type { DecisionMode } from "@/lib/decisionMode";
import { primaryHorizonFromMode } from "@/lib/decisionMode";
import type { InvestorDecisionSummary } from "../InvestorDecisionSummary";
import type { TradingGateRow } from "../retailActionUX";
import {
  activeAlertForTicker,
  addPriceAlert,
  removePriceAlert,
  subscribePriceAlerts,
  type PriceAlert,
} from "@/lib/priceAlerts";
import { currentSignalSince, useTickerTrackRecord } from "@/lib/useTickerTrackRecord";
import { apiUrl } from "@/lib/apiBase";

type Light = "red" | "yellow" | "green" | "neutral";

const TONE: Record<Light, { card: string; text: string; dot: string }> = {
  green: { card: "bg-td-accent-weak/70 border-td-accent/35", text: "text-td-accent", dot: "bg-td-accent" },
  yellow: { card: "bg-td-warn-weak/70 border-td-warn/35", text: "text-td-warn", dot: "bg-td-warn" },
  red: { card: "bg-td-crit-weak/70 border-td-crit/35", text: "text-td-crit", dot: "bg-td-crit" },
  neutral: { card: "bg-td-surface2 border-td-line", text: "text-td-muted", dot: "bg-td-muted" },
};

function usd(n: number | null | undefined, digits = 2): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return `$${n.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits })}`;
}

function pct(from: number, to: number): string {
  const p = ((to - from) / from) * 100;
  return `${p >= 0 ? "+" : "−"}${Math.abs(p).toFixed(1)}%`;
}

function shortDate(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso.length <= 10 ? `${iso}T12:00:00` : iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

/** The one plain sentence — derived from the same light/title the header badge shows. */
export function plainVerdictSentence(light: Light, title: string, entryMode: string | null | undefined, held: boolean): string {
  const t = title.toUpperCase();
  if (light === "green") {
    if (entryMode === "starter_only") return held ? "Add a starter slice only." : "Starter size only. Don't go full size.";
    return held ? "Add in stages. The setup is green." : "Buy in stages. The setup is green.";
  }
  if (light === "red") {
    if (/TRIM|REDUCE|SELL|EXIT|STOP|AVOID/.test(t)) return held ? "Trim. Protect the position." : "Avoid. Don't open a position.";
    return held ? "Hold. Don't add here." : "Don't chase. Wait for the pullback.";
  }
  return held ? "Hold. Don't add today." : "Wait. Don't buy today.";
}

type UnlockRow = { key: string; ok: boolean; label: string; value: string; title?: string };

function gateUnlockLabel(g: TradingGateRow): string {
  if (g.pass) {
    if (g.id === "ml" && g.visualStatus === "unscored") return "ML not scored — no model for this ticker (neutral)";
    if (g.id === "ml") return "ML confidence above floor";
    if (g.id === "regime") return "Market & regime weather";
    return g.label.replace(/\s*\(.*\)$/, "");
  }
  if (g.id === "valuation") return "Valuation clears its margin of safety";
  if (g.id === "regime") return "Weather gate flips to pass";
  if (g.id === "momentum") return "Momentum resets";
  if (g.id === "ml") return "ML confidence clears its floor";
  return `${g.label} clears`;
}

function gateValue(g: TradingGateRow): string {
  if (g.id === "regime" && g.regimeWeatherStatus) return g.pass ? "" : `${g.regimeWeatherStatus} now`;
  if (g.id === "momentum" && g.rsiStatus && !g.pass) return g.rsiStatus;
  if (g.pass) return "";
  const d = g.detail || "";
  return d.length > 34 ? `${d.slice(0, 33)}…` : d;
}

function VerdictActionBar({
  ticker,
  alertLevel,
  currentPrice,
  extra,
}: {
  ticker: string;
  alertLevel: number | null;
  currentPrice: number | null | undefined;
  extra?: ReactNode;
}) {
  const [alert, setAlert] = useState<PriceAlert | null>(null);
  const [notesOpen, setNotesOpen] = useState(false);
  const [note, setNote] = useState("");
  const [noteState, setNoteState] = useState<"idle" | "saving" | "saved" | "error">("idle");

  useEffect(() => {
    const sync = () => setAlert(activeAlertForTicker(ticker));
    sync();
    return subscribePriceAlerts(sync);
  }, [ticker]);

  const saveNote = async () => {
    if (!note.trim()) return;
    setNoteState("saving");
    try {
      const r = await fetch(apiUrl("/api/behavior/journal"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ticker, action: "note", note: note.trim() }),
      });
      if (!r.ok) throw new Error(String(r.status));
      setNoteState("saved");
      setNote("");
    } catch {
      setNoteState("error");
    }
  };

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-2">
        {alert ? (
          <button
            type="button"
            onClick={() => removePriceAlert(alert.id)}
            className="flex-1 min-w-[12rem] inline-flex items-center justify-center gap-2 rounded-xl border border-td-accent/40 bg-td-accent-weak px-4 py-3 text-sm font-semibold text-td-accent hover:bg-td-accent-weak/70"
            title="Remove this price alert"
          >
            <BellOff className="h-4 w-4" />
            Alert set at {usd(alert.price)} · remove
          </button>
        ) : alertLevel != null ? (
          <button
            type="button"
            onClick={() => {
              addPriceAlert(ticker, alertLevel, currentPrice);
              if (typeof Notification !== "undefined" && Notification.permission === "default") {
                void Notification.requestPermission().catch(() => {});
              }
            }}
            className="flex-1 min-w-[12rem] inline-flex items-center justify-center gap-2 rounded-xl bg-td-accent px-4 py-3 text-sm font-bold text-slate-950 hover:brightness-110"
            title="Fires while Thrive Alpha is open (checked against live prices every minute)"
          >
            <Bell className="h-4 w-4" />
            Alert me at {usd(alertLevel)}
          </button>
        ) : null}
        <button
          type="button"
          onClick={() => {
            setNotesOpen((o) => !o);
            setNoteState("idle");
          }}
          aria-expanded={notesOpen}
          className="inline-flex items-center justify-center gap-2 rounded-xl bg-td-surface2 border border-td-line px-4 py-3 text-sm font-semibold text-td-text hover:bg-td-surface2/70"
        >
          <NotebookPen className="h-4 w-4" />
          Notes
        </button>
        {extra}
      </div>
      {notesOpen && (
        <div className="rounded-xl border border-td-line bg-td-surface p-3 space-y-2">
          <label htmlFor={`note-${ticker}`} className="text-[11px] text-td-muted">
            One line for your decision journal — saved to the same log Portfolio shows.
          </label>
          <textarea
            id={`note-${ticker}`}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            rows={2}
            maxLength={500}
            placeholder={`Why you're watching / waiting on ${ticker}…`}
            className="w-full rounded-lg border border-td-line bg-td-bg px-3 py-2 text-sm text-td-text placeholder:text-td-muted/70 focus:border-td-accent focus:outline-none"
          />
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={saveNote}
              disabled={!note.trim() || noteState === "saving"}
              className="rounded-lg bg-td-accent px-3 py-1.5 text-xs font-bold text-slate-950 disabled:opacity-50"
            >
              {noteState === "saving" ? "Saving…" : "Save note"}
            </button>
            {noteState === "saved" && <span className="text-xs text-td-accent">Saved to journal</span>}
            {noteState === "error" && <span className="text-xs text-td-crit">Could not save — try again</span>}
          </div>
        </div>
      )}
    </div>
  );
}

export function VerdictPanel({
  ticker,
  summary,
  mode,
  actionStatus,
  gates,
  gatesPassed,
  gatesTotal,
  currentPrice,
  earnings,
  catalystLabel,
  held,
  onOpenWhy,
  onOpenTrack,
  actionExtra,
}: {
  ticker: string;
  summary: InvestorDecisionSummary;
  mode: DecisionMode;
  actionStatus: { light: Light; title: string; subtitle: string };
  gates: TradingGateRow[];
  gatesPassed: number;
  gatesTotal: number;
  currentPrice: number | null | undefined;
  earnings: { date: string; days_until: number } | null | undefined;
  catalystLabel?: string | null;
  held: boolean;
  onOpenWhy?: () => void;
  onOpenTrack?: () => void;
  actionExtra?: ReactNode;
}) {
  const tone = TONE[actionStatus.light] ?? TONE.neutral;
  const horizonKey = primaryHorizonFromMode(mode);
  const horizon = summary.horizons[horizonKey];
  const ra = summary.retail_action;
  const ez = horizon?.entry_zone;
  const hasBand = ez?.low != null && ez?.high != null && ez.low > 0 && ez.high > 0;
  const price = currentPrice != null && currentPrice > 0 ? currentPrice : null;

  const { data: track, loading: trackLoading } = useTickerTrackRecord(ticker);
  // Daily calls exist for every session; paper-trade rows only on days a paper entry qualified.
  const since = currentSignalSince(
    track?.daily_calls?.length ? track.daily_calls : track?.daily_trades,
  );

  // ── why-in-one-line ─────────────────────────────────────────────
  const blocked = Math.max(0, gatesTotal - gatesPassed);
  let bandClause = "";
  if (hasBand && price != null) {
    const band = `${usd(ez!.low)}–${usd(ez!.high)}`;
    bandClause =
      price > ez!.high
        ? `Price is above the ${band} entry band`
        : price < ez!.low
          ? `Price is below the ${band} entry band`
          : `Price is inside the ${band} entry band`;
  }
  const gateClause =
    gatesTotal > 0 ? (blocked === 0 ? `all ${gatesTotal} gates pass` : `${blocked} of ${gatesTotal} gates are blocked`) : "";
  const whyLine = [bandClause, gateClause].filter(Boolean).join(" and ");

  // ── unlock rows ─────────────────────────────────────────────────
  const rows: UnlockRow[] = [];
  if (hasBand && price != null && price > ez!.high) {
    rows.push({
      key: "band",
      ok: false,
      label: `Price pulls back to ${usd(ez!.low, 0)}–${usd(ez!.high, 0)}`,
      value: `${pct(price, ez!.high)} to ${pct(price, ez!.low)}`,
      title: "Entry band for this horizon — not one of the 4 gates, but the plan only adds inside it.",
    });
  }
  const sortedGates = [...gates].sort((a, b) => Number(a.pass) - Number(b.pass) || (b.blockerWeight ?? 0) - (a.blockerWeight ?? 0));
  for (const g of sortedGates) {
    rows.push({ key: g.id, ok: g.pass, label: gateUnlockLabel(g), value: gateValue(g), title: g.detail });
  }

  // ── tiles ───────────────────────────────────────────────────────
  const rrFromEntry = horizon?.risk_reward_from_entry;
  const rr = rrFromEntry ?? horizon?.risk_reward ?? ra?.rr_ratio ?? null;
  const rrSub = rrFromEntry != null ? "entry band to target" : "spot to target";

  let catalystValue = "None scheduled";
  let catalystSub = "no earnings date in feed";
  if (earnings && earnings.days_until != null && earnings.days_until >= 0) {
    catalystValue = earnings.days_until === 0 ? "Earnings today" : `Earnings ${earnings.days_until}d`;
    catalystSub = `${shortDate(earnings.date)}${held ? " · you hold it" : ""}`;
  } else if (catalystLabel) {
    catalystValue = catalystLabel;
    catalystSub = "active catalyst";
  }
  const earningsSoon = earnings != null && earnings.days_until >= 0 && earnings.days_until <= 14;

  // ── hit rate (same response as the Track tab) ───────────────────
  const cur = track?.current;
  const leg = track?.legacy;
  const curN = cur?.n_observations ?? 0;
  const useCurrent = curN >= 10;
  const hitStats = useCurrent ? cur : (leg?.n_observations ?? 0) > 0 ? leg : curN > 0 ? cur : null;

  // ── alert level: the next price that would change the plan ───────
  let alertLevel: number | null = null;
  if (hasBand && price != null) alertLevel = price > ez!.high ? ez!.high : ez!.low;
  else if (horizon?.stop_loss) alertLevel = horizon.stop_loss;

  return (
    <div className="space-y-3">
      {/* 1 · Verdict */}
      <section className={clsx("rounded-2xl border px-4 sm:px-5 py-4", tone.card)} aria-label="Verdict">
        <p className={clsx("flex items-center gap-2 font-mono text-[11px] font-bold uppercase tracking-wider", tone.text)}>
          <span className={clsx("h-2 w-2 rounded-full", tone.dot)} />
          {actionStatus.title}
        </p>
        <h3 className="mt-2 text-xl sm:text-2xl font-semibold text-td-text leading-tight text-balance">
          {plainVerdictSentence(actionStatus.light, actionStatus.title, ra?.entry_mode, held)}
        </h3>
        {whyLine && <p className="mt-1.5 text-[13.5px] text-td-text/85 leading-snug">{whyLine}.</p>}
        {actionStatus.subtitle && actionStatus.subtitle !== whyLine && (
          <p className="mt-1 text-[12.5px] text-td-muted leading-snug">{actionStatus.subtitle}</p>
        )}
        <p className={clsx("mt-2 text-[11px]", tone.text)}>
          {since ? `Signal ${since.signal} since ${shortDate(since.since)}` : trackLoading ? "Checking signal history…" : "No signal history yet"}
          {" · changes only when a new signal prints"}
        </p>
      </section>

      {/* 2 · Unlocks when */}
      {rows.length > 0 && (
        <section className="rounded-2xl border border-td-line bg-td-surface px-4 sm:px-5 py-3" aria-label="Unlocks when">
          <div className="flex items-baseline justify-between gap-2 mb-1">
            <h4 className="text-[11px] font-semibold uppercase tracking-wider text-td-muted">
              {blocked === 0 && rows.every((r) => r.ok) ? "All clear" : "Unlocks when"}
            </h4>
            <span className="font-mono text-[10.5px] text-td-muted tabular-nums">
              {gatesPassed}/{gatesTotal} gates
            </span>
          </div>
          <ul className="divide-y divide-td-line">
            {rows.map((r) => (
              <li key={r.key} className="flex items-start justify-between gap-3 py-2" title={r.title}>
                <span className="flex items-start gap-2 text-[13px] text-td-text/90 min-w-0">
                  <span className={clsx("font-bold shrink-0", r.ok ? "text-td-accent" : "text-td-crit")} aria-hidden>
                    {r.ok ? "✓" : "✕"}
                  </span>
                  <span className={clsx(r.ok && "text-td-muted")}>{r.label}</span>
                </span>
                {r.value && (
                  <span className="font-mono text-[11px] text-td-muted whitespace-nowrap tabular-nums text-right">{r.value}</span>
                )}
              </li>
            ))}
          </ul>
          {ra?.next_trigger?.headline && (
            <p className="mt-1 pt-2 border-t border-td-line text-[11.5px] text-td-info leading-snug">
              Next: {ra.next_trigger.headline}
              {ra.next_trigger.estimated_days != null ? ` · ~${ra.next_trigger.estimated_days}d` : ""}
            </p>
          )}
          {onOpenWhy && (
            <button
              type="button"
              onClick={onOpenWhy}
              className="mt-1 inline-flex items-center gap-1 text-[11.5px] text-td-muted hover:text-td-accent"
            >
              Gate details <ChevronRight className="h-3 w-3" />
            </button>
          )}
        </section>
      )}

      {/* 3 · Tiles */}
      <div className="grid grid-cols-2 gap-3">
        {/* Hidden entirely when R:R is unknown — a "—" tile teaches nothing. */}
        {rr != null && rr > 0 && (
        <div className="rounded-xl border border-td-line bg-td-surface px-3.5 py-3">
          <p className="text-[11px] text-td-muted">Risk : Reward</p>
          <p className="mt-1 font-mono text-lg font-bold text-td-text tabular-nums">{`1 : ${rr.toFixed(1)}`}</p>
          <p className="text-[10.5px] text-td-muted">
            {rrSub}
            {horizon?.target ? ` · ${usd(horizon.target, 0)}` : ""}
          </p>
        </div>
        )}
        <div
          className={clsx(
            "rounded-xl border px-3.5 py-3",
            earningsSoon ? "border-td-warn/40 bg-td-warn-weak/50" : "border-td-line bg-td-surface",
          )}
        >
          <p className="text-[11px] text-td-muted">Next catalyst</p>
          <p className={clsx("mt-1 font-mono text-[15px] font-bold tabular-nums truncate", earningsSoon ? "text-td-warn" : "text-td-text")}>
            {catalystValue}
          </p>
          <p className="text-[10.5px] text-td-muted truncate">
            {catalystSub}
            {earningsSoon ? " · size down into the print" : ""}
          </p>
        </div>
      </div>

      {/* 4 · Hit rate */}
      <button
        type="button"
        onClick={onOpenTrack}
        className="w-full text-left rounded-xl border border-td-line bg-td-surface px-4 py-3 hover:border-td-accent/40 transition-colors"
      >
        <p className="text-[11px] text-td-muted">Historical hit rate for this ticker</p>
        {hitStats && (hitStats.n_observations ?? 0) > 0 ? (
          <p className="mt-0.5 text-[14px] font-semibold text-td-text">
            <span className={(hitStats.win_rate_pct ?? 0) >= 50 ? "text-td-accent" : "text-td-warn"}>
              {hitStats.win_rate_pct != null ? `${hitStats.win_rate_pct.toFixed(0)}%` : "—"}
            </span>{" "}
            over {hitStats.n_observations} forward-tracked signals
          </p>
        ) : (
          <p className="mt-0.5 text-[13px] text-td-muted">
            {trackLoading ? "Loading track record…" : "No forward-tracked history for this ticker yet."}
          </p>
        )}
        {!useCurrent && hitStats === leg && track?.current_model_version && (
          <p className="mt-1 text-[10.5px] text-td-warn leading-snug">
            Current model {track.current_model_version} is too new for its own read (n={curN}) — this is prior-version history. See Track tab ›
          </p>
        )}
        <p className="mt-1 text-[10px] text-td-muted/80">Based on similar past signals; not a guarantee.</p>
      </button>

      {/* 5 · Actions */}
      <VerdictActionBar ticker={ticker} alertLevel={alertLevel} currentPrice={price} extra={actionExtra} />
    </div>
  );
}
