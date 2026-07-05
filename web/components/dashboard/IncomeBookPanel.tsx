"use client";

import React, { useCallback, useEffect, useState } from "react";
import { Target, RefreshCw, TrendingUp, AlertTriangle, ChevronRight } from "lucide-react";
import { clsx } from "clsx";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

export interface IncomeBookPlan {
  enabled?: boolean;
  as_of?: string | null;
  signal_source?: string;
  universe_size?: number;
  scanned_count?: number;
  candidate_pool_count?: number;
  block_new_entries?: boolean;
  market_regime?: string | null;
  disclaimer?: string;
  settings?: {
    goal_usd?: number;
    timeframe_months?: number;
    capital_usd?: number;
    risk_pct?: number;
    max_open_trades?: number;
    exclude_long_term_holdings?: boolean;
  };
  goal_summary?: {
    goal_usd?: number;
    capital_usd?: number;
    timeframe_months?: number;
    risk_pct?: number;
    risk_per_trade_usd?: number;
    required_return_pct?: number;
    required_monthly_pct?: number;
    feasibility?: "green" | "amber" | "red";
    feasibility_note?: string;
  };
  progress?: {
    realized_pnl_usd?: number;
    unrealized_pnl_usd?: number;
    total_pnl_usd?: number;
    goal_usd?: number;
    pct_of_goal?: number | null;
    open_trades_count?: number;
    closed_trades_count?: number;
  };
  open_trades?: IncomeOpenTrade[];
  proposed_trades?: IncomeCandidate[];
  candidate_pool?: IncomeCandidate[];
  daily_changes?: string[];
  closed_trades?: IncomeClosedTrade[];
  message?: string;
}

export interface IncomeCandidate {
  ticker: string;
  close?: number | null;
  sector?: string;
  swing_setup_label?: string;
  swing_setup_type?: string;
  swing_score?: number;
  gates_passed?: number;
  gates_total?: number;
  gate_cleared?: boolean;
  status?: string;
  entry_low?: number | null;
  entry_high?: number | null;
  stop?: number | null;
  t1?: number | null;
  t2?: number | null;
  swing_rr?: number | null;
  horizon_label?: string;
  sizing?: {
    shares?: number;
    notional_usd?: number;
    risk_usd?: number;
    est_pnl_at_t1_usd?: number | null;
  };
}

export interface IncomeOpenTrade {
  id?: string;
  ticker: string;
  entered_at?: string;
  entry_price?: number;
  shares?: number;
  stop?: number | null;
  t1?: number | null;
  t2?: number | null;
  setup?: string;
  mark_price?: number | null;
  unrealized_pnl_usd?: number;
  unrealized_return_pct?: number;
  today_action?: string;
  gates_passed?: number;
}

export interface IncomeClosedTrade {
  ticker: string;
  realized_pnl_usd?: number;
  return_pct?: number;
  closed_at?: string;
}

function fmtUsd(n: number | null | undefined) {
  if (n == null || Number.isNaN(n)) return "—";
  const sign = n >= 0 ? "+" : "";
  return `${sign}$${Math.abs(n).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

function fmtPct(n: number | null | undefined) {
  if (n == null || Number.isNaN(n)) return "—";
  return `${n >= 0 ? "+" : ""}${n.toFixed(2)}%`;
}

function fmtPrice(n: number | null | undefined) {
  if (n == null) return "—";
  return `$${n.toFixed(2)}`;
}

interface Props {
  onTickerClick?: (ticker: string) => void;
}

export function IncomeBookPanel({ onTickerClick }: Props) {
  const [plan, setPlan] = useState<IncomeBookPlan | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [draft, setDraft] = useState({
    goal_usd: 5000,
    timeframe_months: 3,
    capital_usd: 100000,
    risk_pct: 1.5,
    max_open_trades: 3,
  });

  const fetchPlan = useCallback(async () => {
    setLoading(true);
    setError(null);
    const url = API_BASE ? `${API_BASE}/api/income-book` : "/api/income-book";
    try {
      const r = await fetch(url);
      if (!r.ok) throw new Error(r.status === 503 ? "Load dashboard first, then open Income." : `HTTP ${r.status}`);
      const j = (await r.json()) as IncomeBookPlan;
      setPlan(j);
      if (j.settings) {
        setDraft({
          goal_usd: j.settings.goal_usd ?? 5000,
          timeframe_months: j.settings.timeframe_months ?? 3,
          capital_usd: j.settings.capital_usd ?? 100000,
          risk_pct: j.settings.risk_pct ?? 1.5,
          max_open_trades: j.settings.max_open_trades ?? 3,
        });
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load income book");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchPlan();
  }, [fetchPlan]);

  const postAction = async (body: Record<string, unknown>) => {
    setSaving(true);
    setError(null);
    const url = API_BASE ? `${API_BASE}/api/income-book` : "/api/income-book";
    try {
      const r = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!r.ok) {
        const err = await r.json().catch(() => ({}));
        throw new Error((err as { detail?: string }).detail || `HTTP ${r.status}`);
      }
      setPlan((await r.json()) as IncomeBookPlan);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Action failed");
    } finally {
      setSaving(false);
    }
  };

  const saveSettings = () => {
    postAction({ action: "update_settings", ...draft });
    setSettingsOpen(false);
  };

  const enterFromCandidate = (c: IncomeCandidate) => {
    const entry = c.close ?? c.entry_high ?? c.entry_low;
    if (!entry) return;
    postAction({
      action: "enter_trade",
      ticker: c.ticker,
      entry_price: entry,
      stop: c.stop,
      t1: c.t1,
      t2: c.t2,
      setup: c.swing_setup_type,
      notional_usd: c.sizing?.notional_usd,
    });
  };

  const closeTrade = (t: IncomeOpenTrade) => {
    const exit = t.mark_price ?? t.entry_price;
    if (!exit) return;
    postAction({
      action: "close_trade",
      trade_id: t.id,
      ticker: t.ticker,
      exit_price: exit,
      exit_reason: t.today_action || "manual",
    });
  };

  if (loading && !plan) {
    return (
      <div className="rounded-xl border border-slate-700 bg-slate-900/40 p-8 text-center text-slate-400">
        Loading income plan…
      </div>
    );
  }

  if (plan?.enabled === false) {
    return (
      <div className="rounded-xl border border-slate-700 bg-slate-900/40 p-6 text-slate-400">
        {plan.message || "Income book disabled in config."}
      </div>
    );
  }

  const gs = plan?.goal_summary;
  const prog = plan?.progress;
  const feasibility = gs?.feasibility ?? "green";

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-emerald-500/30 bg-gradient-to-br from-emerald-950/40 to-slate-900/60 p-4 sm:p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2 text-emerald-300">
              <Target className="h-5 w-5" />
              <h2 className="text-lg font-semibold">Income Book</h2>
            </div>
            <p className="text-sm text-slate-400 mt-1 max-w-2xl">
              Separate tactical sleeve — fresh swing picks from the ~100-ticker universe. Not your long-term portfolio.
            </p>
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => setSettingsOpen((v) => !v)}
              className="px-3 py-1.5 rounded-lg text-sm border border-slate-600 text-slate-300 hover:bg-slate-800"
            >
              Edit goal
            </button>
            <button
              type="button"
              onClick={fetchPlan}
              disabled={loading || saving}
              className="px-3 py-1.5 rounded-lg text-sm border border-emerald-600/50 text-emerald-300 hover:bg-emerald-500/10 flex items-center gap-1"
            >
              <RefreshCw className={clsx("h-4 w-4", loading && "animate-spin")} />
              Refresh
            </button>
          </div>
        </div>

        {settingsOpen && (
          <div className="mt-4 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 p-3 rounded-lg bg-slate-900/80 border border-slate-700">
            {(
              [
                ["goal_usd", "Goal ($)", 500],
                ["capital_usd", "Capital ($)", 50000],
                ["timeframe_months", "Months", 1],
                ["risk_pct", "Risk % / trade", 0.5],
                ["max_open_trades", "Max open", 1],
              ] as const
            ).map(([key, label, step]) => (
              <label key={key} className="text-xs text-slate-400">
                {label}
                <input
                  type="number"
                  step={step}
                  value={draft[key]}
                  onChange={(e) => setDraft((d) => ({ ...d, [key]: Number(e.target.value) }))}
                  className="mt-1 w-full rounded bg-slate-800 border border-slate-600 px-2 py-1.5 text-sm text-slate-100"
                />
              </label>
            ))}
            <div className="col-span-full flex justify-end">
              <button
                type="button"
                onClick={saveSettings}
                disabled={saving}
                className="px-4 py-1.5 rounded-lg bg-emerald-600 text-white text-sm hover:bg-emerald-500"
              >
                Save settings
              </button>
            </div>
          </div>
        )}

        <div className="mt-4 grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
          <StatCard label="Target" value={fmtUsd(gs?.goal_usd)} sub={`${gs?.timeframe_months ?? 3} months`} />
          <StatCard
            label="Progress"
            value={fmtUsd(prog?.total_pnl_usd)}
            sub={prog?.pct_of_goal != null ? `${prog.pct_of_goal}% of goal` : undefined}
            valueClass={
              (prog?.total_pnl_usd ?? 0) >= 0 ? "text-emerald-400" : "text-red-400"
            }
          />
          <StatCard
            label="Required return"
            value={gs?.required_return_pct != null ? `${gs.required_return_pct}%` : "—"}
            sub={gs?.required_monthly_pct != null ? `~${gs.required_monthly_pct}%/mo` : undefined}
          />
          <StatCard
            label="Risk / trade"
            value={fmtUsd(gs?.risk_per_trade_usd)}
            sub={`${gs?.risk_pct ?? 1.5}% of ${fmtUsd(gs?.capital_usd).replace("+", "")}`}
          />
        </div>

        {gs?.feasibility_note && (
          <div
            className={clsx(
              "mt-3 rounded-lg px-3 py-2 text-sm border",
              feasibility === "green" && "border-emerald-500/30 bg-emerald-500/10 text-emerald-100",
              feasibility === "amber" && "border-amber-500/30 bg-amber-500/10 text-amber-100",
              feasibility === "red" && "border-red-500/30 bg-red-500/10 text-red-100",
            )}
          >
            {gs.feasibility_note}
          </div>
        )}

        {plan?.block_new_entries && (
          <div className="mt-2 flex items-center gap-2 text-amber-200 text-sm">
            <AlertTriangle className="h-4 w-4 shrink-0" />
            Market regime DOWN — manage open trades only; no new entries recommended.
          </div>
        )}

        <p className="mt-2 text-[11px] text-slate-500">
          Scanned {plan?.scanned_count ?? 0} of {plan?.universe_size ?? 0} tickers ({plan?.signal_source}) ·{" "}
          {plan?.candidate_pool_count ?? 0} swing candidates · as-of {plan?.as_of ?? "—"}
        </p>
      </div>

      {error && (
        <div className="rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-200">{error}</div>
      )}

      {plan?.daily_changes && plan.daily_changes.length > 0 && (
        <section className="rounded-xl border border-slate-700 bg-slate-900/30 p-4">
          <h3 className="text-sm font-medium text-slate-300 mb-2">Today&apos;s changes</h3>
          <ul className="space-y-1 text-sm text-slate-400">
            {plan.daily_changes.map((line, i) => (
              <li key={i}>{line}</li>
            ))}
          </ul>
        </section>
      )}

      {(plan?.open_trades?.length ?? 0) > 0 && (
        <section>
          <SectionTitle icon={<TrendingUp className="h-4 w-4" />} title="Open income trades" />
          <TradeTable
            rows={plan!.open_trades!}
            mode="open"
            onTickerClick={onTickerClick}
            onClose={closeTrade}
            saving={saving}
          />
        </section>
      )}

      <section>
        <SectionTitle
          icon={<ChevronRight className="h-4 w-4" />}
          title="Proposed game plan"
          sub="Swing setups from universe (excludes long-term holdings by default)"
        />
        {(plan?.proposed_trades?.length ?? 0) === 0 ? (
          <div className="rounded-xl border border-slate-700 bg-slate-900/30 p-6 text-center text-slate-400 text-sm">
            No qualifying swing setups today. Refresh after EOD run or relax min_swing_score in config.
          </div>
        ) : (
          <CandidateTable
            rows={plan!.proposed_trades!}
            onTickerClick={onTickerClick}
            onEnter={enterFromCandidate}
            saving={saving}
            blockNew={plan?.block_new_entries}
            openCount={plan?.open_trades?.length ?? 0}
            maxOpen={plan?.settings?.max_open_trades ?? 3}
          />
        )}
      </section>

      {(plan?.closed_trades?.length ?? 0) > 0 && (
        <section>
          <SectionTitle title="Recent closed" />
          <div className="rounded-xl border border-slate-700 overflow-hidden text-sm">
            <table className="w-full">
              <thead className="text-slate-500 text-left bg-slate-800/50">
                <tr>
                  <th className="px-3 py-2">Ticker</th>
                  <th className="px-3 py-2">Closed</th>
                  <th className="px-3 py-2">P&amp;L</th>
                  <th className="px-3 py-2">Return</th>
                </tr>
              </thead>
              <tbody>
                {plan!.closed_trades!.slice().reverse().map((t, i) => (
                  <tr key={i} className="border-t border-slate-700/50">
                    <td className="px-3 py-2 font-mono text-emerald-400">{t.ticker}</td>
                    <td className="px-3 py-2 text-slate-400">{t.closed_at}</td>
                    <td className={clsx("px-3 py-2", (t.realized_pnl_usd ?? 0) >= 0 ? "text-emerald-400" : "text-red-400")}>
                      {fmtUsd(t.realized_pnl_usd)}
                    </td>
                    <td className="px-3 py-2">{fmtPct(t.return_pct)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <p className="text-[10px] text-slate-600 leading-snug">{plan?.disclaimer}</p>
    </div>
  );
}

function StatCard({
  label,
  value,
  sub,
  valueClass = "text-slate-100",
}: {
  label: string;
  value: string;
  sub?: string;
  valueClass?: string;
}) {
  return (
    <div className="rounded-lg bg-slate-900/60 border border-slate-700/80 px-3 py-2">
      <div className="text-[10px] uppercase tracking-wide text-slate-500">{label}</div>
      <div className={clsx("text-lg font-semibold mt-0.5", valueClass)}>{value}</div>
      {sub && <div className="text-xs text-slate-500">{sub}</div>}
    </div>
  );
}

function SectionTitle({
  icon,
  title,
  sub,
}: {
  icon?: React.ReactNode;
  title: string;
  sub?: string;
}) {
  return (
    <div className="flex items-center gap-2 mb-2">
      {icon && <span className="text-emerald-500">{icon}</span>}
      <h3 className="text-sm font-medium text-slate-200">{title}</h3>
      {sub && <span className="text-xs text-slate-500">— {sub}</span>}
    </div>
  );
}

function CandidateTable({
  rows,
  onTickerClick,
  onEnter,
  saving,
  blockNew,
  openCount,
  maxOpen,
}: {
  rows: IncomeCandidate[];
  onTickerClick?: (t: string) => void;
  onEnter: (c: IncomeCandidate) => void;
  saving: boolean;
  blockNew?: boolean;
  openCount: number;
  maxOpen: number;
}) {
  return (
    <div className="rounded-xl border border-slate-700 overflow-x-auto">
      <table className="w-full min-w-[900px] text-sm">
        <thead className="text-slate-400 text-left bg-slate-800/60">
          <tr>
            <th className="px-3 py-2">Ticker</th>
            <th className="px-3 py-2">Setup</th>
            <th className="px-3 py-2">Status</th>
            <th className="px-3 py-2">Entry zone</th>
            <th className="px-3 py-2">Stop</th>
            <th className="px-3 py-2">T1 / T2</th>
            <th className="px-3 py-2">Size</th>
            <th className="px-3 py-2">Gates</th>
            <th className="px-3 py-2"></th>
          </tr>
        </thead>
        <tbody>
          {rows.map((c) => (
            <tr key={c.ticker} className="border-t border-slate-700/50 hover:bg-slate-800/20">
              <td className="px-3 py-2">
                <button
                  type="button"
                  onClick={() => onTickerClick?.(c.ticker)}
                  className="font-mono text-emerald-400 hover:underline"
                >
                  {c.ticker}
                </button>
                <div className="text-xs text-slate-500">{c.sector}</div>
              </td>
              <td className="px-3 py-2">
                <div>{c.swing_setup_label || c.swing_setup_type}</div>
                <div className="text-xs text-slate-500">Score {c.swing_score?.toFixed(0)} · R:R {c.swing_rr?.toFixed(1) ?? "—"}</div>
              </td>
              <td className="px-3 py-2">
                <StatusBadge status={c.status} />
              </td>
              <td className="px-3 py-2 font-mono text-xs">
                {fmtPrice(c.entry_low)} – {fmtPrice(c.entry_high)}
                <div className="text-slate-500">Spot {fmtPrice(c.close)}</div>
              </td>
              <td className="px-3 py-2 font-mono">{fmtPrice(c.stop)}</td>
              <td className="px-3 py-2 font-mono text-xs">
                {fmtPrice(c.t1)} / {fmtPrice(c.t2)}
              </td>
              <td className="px-3 py-2 text-xs">
                {c.sizing?.shares ? `${c.sizing.shares} sh · ${fmtUsd(c.sizing.notional_usd)}` : "—"}
                {c.sizing?.est_pnl_at_t1_usd != null && (
                  <div className="text-slate-500">Est @ T1 {fmtUsd(c.sizing.est_pnl_at_t1_usd)}</div>
                )}
              </td>
              <td className="px-3 py-2 text-xs">
                {c.gates_passed}/{c.gates_total}
                {c.gate_cleared && <span className="text-emerald-500 ml-1">GO</span>}
              </td>
              <td className="px-3 py-2">
                <button
                  type="button"
                  disabled={saving || blockNew || openCount >= maxOpen}
                  onClick={() => onEnter(c)}
                  className="px-2 py-1 rounded text-xs bg-emerald-600/80 text-white hover:bg-emerald-500 disabled:opacity-40"
                  title={blockNew ? "Regime blocks new entries" : openCount >= maxOpen ? "Max open trades" : "Log entry in income book"}
                >
                  I entered
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function TradeTable({
  rows,
  mode,
  onTickerClick,
  onClose,
  saving,
}: {
  rows: IncomeOpenTrade[];
  mode: "open";
  onTickerClick?: (t: string) => void;
  onClose: (t: IncomeOpenTrade) => void;
  saving: boolean;
}) {
  return (
    <div className="rounded-xl border border-slate-700 overflow-x-auto">
      <table className="w-full min-w-[720px] text-sm">
        <thead className="text-slate-400 text-left bg-slate-800/60">
          <tr>
            <th className="px-3 py-2">Ticker</th>
            <th className="px-3 py-2">Entry</th>
            <th className="px-3 py-2">Mark</th>
            <th className="px-3 py-2">Stop / T1</th>
            <th className="px-3 py-2">P&amp;L</th>
            <th className="px-3 py-2">Action</th>
            <th className="px-3 py-2"></th>
          </tr>
        </thead>
        <tbody>
          {rows.map((t) => (
            <tr key={t.id || t.ticker} className="border-t border-slate-700/50">
              <td className="px-3 py-2">
                <button type="button" onClick={() => onTickerClick?.(t.ticker)} className="font-mono text-emerald-400 hover:underline">
                  {t.ticker}
                </button>
              </td>
              <td className="px-3 py-2 font-mono">{fmtPrice(t.entry_price)}</td>
              <td className="px-3 py-2 font-mono">{fmtPrice(t.mark_price)}</td>
              <td className="px-3 py-2 font-mono text-xs">
                {fmtPrice(t.stop)} / {fmtPrice(t.t1)}
              </td>
              <td className={clsx("px-3 py-2", (t.unrealized_pnl_usd ?? 0) >= 0 ? "text-emerald-400" : "text-red-400")}>
                {fmtUsd(t.unrealized_pnl_usd)} ({fmtPct(t.unrealized_return_pct)})
              </td>
              <td className="px-3 py-2 text-xs text-amber-200">{actionLabel(t.today_action)}</td>
              <td className="px-3 py-2">
                <button
                  type="button"
                  disabled={saving}
                  onClick={() => onClose(t)}
                  className="px-2 py-1 rounded text-xs border border-slate-600 text-slate-300 hover:bg-slate-800"
                >
                  Close
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function StatusBadge({ status }: { status?: string }) {
  const s = status || "watch";
  const cls =
    s === "ready"
      ? "bg-emerald-500/20 text-emerald-300"
      : s === "watch"
        ? "bg-slate-600/40 text-slate-300"
        : "bg-amber-500/20 text-amber-200";
  return <span className={clsx("px-2 py-0.5 rounded text-xs font-medium uppercase", cls)}>{s}</span>;
}

function actionLabel(a?: string) {
  switch (a) {
    case "trim_t1":
      return "Trim ~⅓ at T1";
    case "exit_stop":
      return "Exit — stop";
    case "exit_gates_broke":
      return "Exit — gates broke";
    case "hold":
      return "Hold";
    default:
      return a || "—";
  }
}
