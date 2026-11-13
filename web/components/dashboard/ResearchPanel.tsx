"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { clsx } from "clsx";
import { Download, FlaskConical, Play, Plus, Trash2 } from "lucide-react";
import { Area, CartesianGrid, ComposedChart, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { apiUrl } from "@/lib/apiBase";

type Num = number | null | undefined;
interface FieldDef { name: string; label: string; group: string; unit: string; help: string; rankable: boolean }
interface Cond { field: string; op: string; value: string; value2: string; valueField: string; useField: boolean }
type Rule = Record<string, unknown>;
interface Stats { n: number; win_rate?: Num; mean?: Num; median?: Num; avg_win?: Num; avg_loss?: Num; payoff?: Num; worst?: Num; best?: Num; vs_spy?: Num; vs_random?: Num }

const OPS: { id: string; label: string }[] = [
  { id: ">", label: ">" }, { id: ">=", label: "≥" }, { id: "<", label: "<" }, { id: "<=", label: "≤" },
  { id: "between", label: "between" }, { id: "top_pct", label: "top %" }, { id: "bottom_pct", label: "bottom %" },
  { id: "crosses_above", label: "crosses above" }, { id: "crosses_below", label: "crosses below" },
  { id: "in", label: "is" }, { id: "not_in", label: "is not" },
];
const ITEM_CODES: [string, string][] = [
  ["1.01", "Material agreement"], ["1.02", "Agreement terminated"], ["2.01", "Acquisition/sale done"], ["2.02", "Earnings results"],
  ["2.05", "Restructuring"], ["2.06", "Impairment"], ["4.01", "Auditor change"], ["4.02", "Restatement"], ["5.02", "Officer/director change"], ["8.01", "Other event"],
];
const c = (field: string, op: string, value: string, extra: Partial<Cond> = {}): Cond => ({ field, op, value, value2: "", valueField: "", useField: false, ...extra });
const PRESETS: { name: string; join: "all" | "any"; conds: Cond[] }[] = [
  { name: "Pullback in an uptrend", join: "all", conds: [c("dist_sma200", ">", "0"), c("rsi14", "<", "35")] },
  { name: "Momentum leaders", join: "all", conds: [c("mom_12_1", "top_pct", "10"), c("dist_sma50", ">", "0")] },
  { name: "Uptrend template", join: "all", conds: [c("trend_template", ">=", "1")] },
  { name: "Falling knife", join: "all", conds: [c("dist_sma200", "<", "-15"), c("rsi14", "<", "30")] },
  { name: "New 52-week high on volume", join: "all", conds: [c("dd_52w", ">=", "0"), c("vol_ratio", ">", "1.5")] },
  { name: "Golden cross", join: "all", conds: [c("sma50_over_200", "crosses_above", "0.5")] },
  { name: "Big gap down", join: "all", conds: [c("gap_pct", "<", "-5")] },
];

const fmt = (v: Num, d = 1, suf = "") => (v == null || Number.isNaN(v) ? "—" : `${Number(v).toFixed(d)}${suf}`);
const tone = (v: Num) => (v == null ? "text-td-muted" : v > 0 ? "text-emerald-400" : v < 0 ? "text-red-400" : "text-td-text");

function toRule(conds: Cond[], join: "all" | "any"): Rule {
  const parts = conds.map((k) => {
    if (k.field === "sector") return { field: "sector", op: k.op === "not_in" ? "not_in" : "in", value: k.value.split(",").map((s) => s.trim()).filter(Boolean) };
    if (k.useField) return { field: k.field, op: k.op, value_field: k.valueField };
    if (k.op === "between") return { field: k.field, op: k.op, value: [Number(k.value), Number(k.value2)] };
    return { field: k.field, op: k.op, value: Number(k.value) };
  });
  return { [join]: parts };
}

function fromRule(rule: Rule): { join: "all" | "any"; conds: Cond[] } {
  const join = "any" in rule ? "any" : "all";
  const list = ((rule[join] as Record<string, unknown>[]) || [rule]).filter(Boolean);
  return {
    join,
    conds: list.map((r) => {
      const v = r.value as unknown;
      if (r.field === "sector") return c("sector", String(r.op), ((v as string[]) || []).join(", "));
      if (r.value_field) return c(String(r.field), String(r.op), "", { useField: true, valueField: String(r.value_field) });
      if (Array.isArray(v)) return c(String(r.field), "between", String(v[0]), { value2: String(v[1]) });
      return c(String(r.field), String(r.op), String(v ?? ""));
    }),
  };
}

function downloadCsv(name: string, rows: Record<string, unknown>[]) {
  if (!rows.length) return;
  const cols = Array.from(new Set(rows.flatMap((r) => Object.keys(r))));
  const esc = (v: unknown) => {
    const s = v == null ? "" : typeof v === "object" ? JSON.stringify(v) : String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const csv = [cols.join(","), ...rows.map((r) => cols.map((k) => esc(r[k])).join(","))].join("\n");
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
  a.download = name;
  a.click();
  URL.revokeObjectURL(a.href);
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(apiUrl(path), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(typeof j.detail === "string" ? j.detail : `Request failed (${r.status})`);
  return j as T;
}

async function runJob<T>(path: string, body: unknown, onState: (s: string) => void): Promise<T> {
  let job = await postJson<{ id: string; state: string; result?: T; error?: string }>(path, body);
  const t0 = Date.now();
  while (job.state === "queued" || job.state === "running") {
    onState(job.state === "queued" ? "Queued…" : `Running… ${Math.round((Date.now() - t0) / 1000)}s`);
    if (Date.now() - t0 > 5 * 60_000) throw new Error("Timed out after 5 minutes");
    await new Promise((res) => setTimeout(res, 1500));
    const r = await fetch(apiUrl(`/api/research/jobs/${job.id}`));
    if (!r.ok) throw new Error("Lost the job (the server may have restarted). Run it again.");
    job = await r.json();
  }
  if (job.state === "error") throw new Error(job.error || "Run failed");
  return job.result as T;
}

function useFields() {
  const [fields, setFields] = useState<FieldDef[]>([]);
  const [sectors, setSectors] = useState<string[]>([]);
  const [status, setStatus] = useState<{ meta?: { as_of?: string; n_tickers?: number; start?: string; excluded_bad_history?: string[] }; state?: string } | null>(null);
  useEffect(() => {
    fetch(apiUrl("/api/research/fields")).then((r) => r.json()).then((j) => setFields(j.fields || [])).catch(() => {});
    fetch(apiUrl("/api/research/status")).then((r) => r.json()).then(setStatus).catch(() => {});
    fetch(apiUrl("/api/research/sectors")).then((r) => (r.ok ? r.json() : { sectors: [] })).then((j) => setSectors(j.sectors || [])).catch(() => {});
  }, []);
  return { fields, sectors, status };
}

const inputCls = "rounded-md border border-td-line bg-td-surface2 px-2 py-1 text-[13px] text-td-text";
const btnCls = "inline-flex items-center gap-1.5 rounded-md border border-td-line px-2.5 py-1 text-[13px] text-td-text hover:bg-td-surface2 disabled:opacity-50";

function RuleBuilder({ fields, sectors, conds, setConds, join, setJoin }: {
  fields: FieldDef[]; sectors: string[]; conds: Cond[]; setConds: (c: Cond[]) => void; join: "all" | "any"; setJoin: (j: "all" | "any") => void;
}) {
  const groups = useMemo(() => Array.from(new Set(fields.map((f) => f.group))), [fields]);
  const upd = (i: number, patch: Partial<Cond>) => setConds(conds.map((k, j) => (j === i ? { ...k, ...patch } : k)));
  const fieldSelect = (value: string, onChange: (v: string) => void, withSector = false) => (
    <select className={inputCls} value={value} onChange={(e) => onChange(e.target.value)}>
      {groups.map((g) => (
        <optgroup key={g} label={g}>
          {fields.filter((f) => f.group === g).map((f) => <option key={f.name} value={f.name}>{f.label}{f.unit && f.unit !== "0/1" ? ` (${f.unit})` : ""}</option>)}
        </optgroup>
      ))}
      {withSector && <option value="sector">Sector</option>}
    </select>
  );
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2 text-[13px] text-td-muted">
        <span>Preset</span>
        <select className={inputCls} value="" onChange={(e) => { const p = PRESETS.find((x) => x.name === e.target.value); if (p) { setConds(p.conds.map((k) => ({ ...k }))); setJoin(p.join); } }}>
          <option value="">Choose…</option>
          {PRESETS.map((p) => <option key={p.name}>{p.name}</option>)}
        </select>
        <span className="ml-2">Match</span>
        <select className={inputCls} value={join} onChange={(e) => setJoin(e.target.value as "all" | "any")}>
          <option value="all">all conditions (AND)</option>
          <option value="any">any condition (OR)</option>
        </select>
      </div>
      {conds.map((k, i) => {
        const f = fields.find((x) => x.name === k.field);
        const ops = k.field === "sector" ? OPS.filter((o) => o.id === "in" || o.id === "not_in")
          : OPS.filter((o) => !["in", "not_in"].includes(o.id) && (f?.rankable || !o.id.endsWith("_pct")));
        return (
          <div key={i} className="flex flex-wrap items-center gap-2">
            {fieldSelect(k.field, (v) => upd(i, { field: v, op: v === "sector" ? "in" : k.op === "in" || k.op === "not_in" ? ">" : k.op, value: v === "sector" ? sectors[0] || "" : k.value }), true)}
            <select className={inputCls} value={k.op} onChange={(e) => upd(i, { op: e.target.value })}>
              {ops.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
            </select>
            {k.field === "sector" ? (
              <select className={inputCls} value={k.value} onChange={(e) => upd(i, { value: e.target.value })}>
                {sectors.map((s) => <option key={s}>{s}</option>)}
              </select>
            ) : k.useField ? (
              fieldSelect(k.valueField || k.field, (v) => upd(i, { valueField: v }))
            ) : (
              <>
                <input className={clsx(inputCls, "w-20")} inputMode="decimal" value={k.value} onChange={(e) => upd(i, { value: e.target.value })} />
                {k.op === "between" && <><span className="text-td-muted text-[13px]">and</span><input className={clsx(inputCls, "w-20")} inputMode="decimal" value={k.value2} onChange={(e) => upd(i, { value2: e.target.value })} /></>}
              </>
            )}
            {k.field !== "sector" && [">", ">=", "<", "<=", "crosses_above", "crosses_below"].includes(k.op) && (
              <label className="text-[12px] text-td-muted inline-flex items-center gap-1">
                <input type="checkbox" checked={k.useField} onChange={(e) => upd(i, { useField: e.target.checked, valueField: k.valueField || "dist_sma50" })} /> vs field
              </label>
            )}
            <button className="text-td-muted hover:text-red-400" onClick={() => setConds(conds.filter((_, j) => j !== i))} aria-label="Remove condition"><Trash2 className="h-4 w-4" /></button>
            {f?.help && <span className="basis-full text-[11px] text-td-muted">{f.help}</span>}
          </div>
        );
      })}
      <button className={btnCls} disabled={conds.length >= 12} onClick={() => setConds([...conds, c("rsi14", "<", "30")])}><Plus className="h-4 w-4" /> Add condition</button>
    </div>
  );
}

function StatTable({ rows }: { rows: [string, Stats | undefined][] }) {
  const cols: [keyof Stats, string, number, string][] = [["n", "Trades", 0, ""], ["win_rate", "Win %", 1, "%"], ["mean", "Avg", 2, "%"], ["avg_win", "Avg win", 2, "%"], ["avg_loss", "Avg loss", 2, "%"], ["payoff", "Win/loss", 2, "x"], ["worst", "Worst", 1, "%"], ["vs_spy", "vs SPY", 2, "%"], ["vs_random", "vs random pick", 2, "%"]];
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[13px]">
        <thead><tr className="text-td-muted text-left">{["", ...cols.map((x) => x[1])].map((h) => <th key={h} className="py-1 pr-3 font-normal">{h}</th>)}</tr></thead>
        <tbody>
          {rows.filter(([, s]) => s).map(([name, s]) => (
            <tr key={name} className="border-t border-td-line">
              <td className="py-1 pr-3 text-td-muted">{name}</td>
              {cols.map(([k, , d, suf]) => <td key={k} className={clsx("py-1 pr-3 tabular-nums", k !== "n" && k !== "win_rate" && k !== "payoff" ? tone(s?.[k] as Num) : "text-td-text")}>{k === "n" ? s?.n ?? 0 : fmt(s?.[k] as Num, d, suf)}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

interface Promotion { n: number; mean_net_pct?: Num; t_stat?: Num; deflated_sharpe?: { dsr?: Num }; pbo?: Num; passes: boolean; fails: string[]; n_trials: number; beats_baseline_pct?: Num }
interface BtResult {
  rule_text: string; params: Record<string, unknown>; all: Stats; in_sample?: Stats; out_of_sample?: Stats; promotion: Promotion;
  portfolio: { cagr: Num; spy_cagr: Num; max_dd: Num; spy_max_dd: Num; sharpe: Num; exposure_pct: Num; avg_open: Num; note: string };
  curve: { dates: string[]; strategy: Num[]; spy: Num[] }; by_year?: (Stats & { year: number })[]; by_sector?: (Stats & { sector: string })[];
  exit_reasons: Record<string, number>; trades: Record<string, unknown>[]; trades_total: number; open_trades: number; panel: { as_of?: string; n_tickers?: number; missing_n?: number };
}

function PromotionBox({ p }: { p: Promotion }) {
  return (
    <div className={clsx("rounded-lg border p-3 text-[13px]", p.passes ? "border-emerald-500/40 bg-emerald-500/5" : "border-td-warn/40 bg-td-warn/5")}>
      <div className={clsx("font-semibold", p.passes ? "text-emerald-400" : "text-td-warn")}>{p.passes ? "Clears the promotion bar (out of sample)" : "Watch: does not clear the promotion bar"}</div>
      <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-td-text tabular-nums">
        <span>Trades {p.n}</span><span>Avg after costs {fmt(p.mean_net_pct, 2, "%")}</span><span>t-stat {fmt(p.t_stat, 2)} (need ≥3)</span>
        <span>Deflated Sharpe {fmt(p.deflated_sharpe?.dsr, 2)} (need ≥0.95)</span><span>Overfitting odds {p.pbo == null ? "—" : `${Math.round(p.pbo * 100)}%`}</span>
        <span>vs random pick {fmt(p.beats_baseline_pct, 2, "%")}</span><span>Tries of this idea {p.n_trials}</span>
      </div>
      {!p.passes && p.fails?.length > 0 && <ul className="mt-1 list-disc pl-5 text-td-muted">{p.fails.map((f) => <li key={f}>{f}</li>)}</ul>}
      <p className="mt-1 text-[11px] text-td-muted">Research only. A rule changes BUY/HOLD/SELL only after this bar and your approval.</p>
    </div>
  );
}

function Tester({ fields, sectors, initial }: { fields: FieldDef[]; sectors: string[]; initial?: { rule: Rule; params?: Record<string, unknown> } | null }) {
  const [conds, setConds] = useState<Cond[]>(PRESETS[0].conds);
  const [join, setJoin] = useState<"all" | "any">("all");
  const [p, setP] = useState({ hold_days: "20", stop_pct: "8", target_pct: "", cost_bps: "10", entry: "on_change", split_date: "2019-01-01", label: "" });
  const [res, setRes] = useState<BtResult | null>(null);
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  useEffect(() => {
    if (!initial) return;
    const r = fromRule(initial.rule);
    setConds(r.conds); setJoin(r.join);
    const q = initial.params || {};
    setP((o) => ({ ...o, hold_days: String(q.hold_days ?? o.hold_days), stop_pct: q.stop_pct == null ? "" : String(q.stop_pct), target_pct: q.target_pct == null ? "" : String(q.target_pct), cost_bps: String(q.cost_bps ?? o.cost_bps), entry: String(q.entry ?? o.entry), split_date: String(q.split_date ?? o.split_date) }));
  }, [initial]);
  const run = async () => {
    setErr(""); setRes(null);
    try {
      const body = { rule: toRule(conds, join), hold_days: Number(p.hold_days), stop_pct: p.stop_pct ? Number(p.stop_pct) : null, target_pct: p.target_pct ? Number(p.target_pct) : null, cost_bps: Number(p.cost_bps), entry: p.entry, split_date: p.split_date || null, label: p.label || null };
      setRes(await runJob<BtResult>("/api/research/backtest", body, setBusy));
    } catch (e) { setErr((e as Error).message); } finally { setBusy(""); }
  };
  const curve = res ? res.curve.dates.map((d, i) => ({ d, Rule: res.curve.strategy[i], SPY: res.curve.spy[i] })) : [];
  const num = (k: keyof typeof p, label: string, w = "w-16") => (
    <label className="inline-flex items-center gap-1 text-[13px] text-td-muted">{label}<input className={clsx(inputCls, w)} value={p[k]} onChange={(e) => setP({ ...p, [k]: e.target.value })} /></label>
  );
  return (
    <div className="space-y-3">
      <RuleBuilder fields={fields} sectors={sectors} conds={conds} setConds={setConds} join={join} setJoin={setJoin} />
      <div className="flex flex-wrap items-center gap-3">
        {num("hold_days", "Hold days")}{num("stop_pct", "Stop %")}{num("target_pct", "Target %")}{num("cost_bps", "Cost bps")}
        <label className="inline-flex items-center gap-1 text-[13px] text-td-muted">Entries
          <select className={inputCls} value={p.entry} onChange={(e) => setP({ ...p, entry: e.target.value })}><option value="on_change">when rule turns on</option><option value="every">every day it's on</option></select>
        </label>
        {num("split_date", "Out-of-sample from", "w-28")}{num("label", "Name", "w-32")}
        <button className={btnCls} onClick={run} disabled={!!busy || !conds.length}><Play className="h-4 w-4" /> {busy || "Run test"}</button>
      </div>
      <p className="text-[11px] text-td-muted">Signal at the close, buy next open, sell at stop, target or after the hold. Same-day stop and target counts as the stop. Only stocks in the S&P 500 on that date.</p>
      {err && <p className="text-[13px] text-red-400">{err}</p>}
      {res && (
        <div className="space-y-3">
          <p className="text-[13px] text-td-text"><span className="text-td-muted">Rule:</span> {res.rule_text} · {String(res.params.start)} → {String(res.params.end)} · {res.panel.n_tickers} stocks with data</p>
          <PromotionBox p={res.promotion} />
          <StatTable rows={[["All", res.all], ["Before split", res.in_sample], ["After split", res.out_of_sample]]} />
          <div className="flex flex-wrap gap-x-4 text-[13px] tabular-nums text-td-text">
            <span>Per year {fmt(res.portfolio.cagr, 1, "%")} vs SPY {fmt(res.portfolio.spy_cagr, 1, "%")}</span>
            <span>Worst drop {fmt(res.portfolio.max_dd, 0, "%")} vs SPY {fmt(res.portfolio.spy_max_dd, 0, "%")}</span>
            <span>Sharpe {fmt(res.portfolio.sharpe, 2)}</span><span>Invested {fmt(res.portfolio.exposure_pct, 0, "%")} of days</span>
            <span>Exits: {Object.entries(res.exit_reasons).map(([k, v]) => `${k} ${v}`).join(", ")}</span>
          </div>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={curve}>
                <CartesianGrid stroke="#334155" strokeDasharray="3 3" />
                <XAxis dataKey="d" tick={{ fontSize: 11, fill: "#94a3b8" }} minTickGap={40} />
                <YAxis tick={{ fontSize: 11, fill: "#94a3b8" }} scale="log" domain={["auto", "auto"]} />
                <Tooltip contentStyle={{ backgroundColor: "#1e293b", border: "1px solid #334155", borderRadius: 8 }} />
                <Legend />
                <Line dataKey="Rule" stroke="#34d399" dot={false} strokeWidth={2} />
                <Line dataKey="SPY" stroke="#94a3b8" dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <p className="text-[11px] text-td-muted">{res.portfolio.note}</p>
          {res.by_year && <details><summary className="cursor-pointer text-[13px] text-td-text">By year</summary><StatTable rows={res.by_year.map((y) => [String(y.year), y])} /></details>}
          {res.by_sector && <details><summary className="cursor-pointer text-[13px] text-td-text">By sector</summary><StatTable rows={res.by_sector.map((y) => [y.sector, y])} /></details>}
          <details>
            <summary className="cursor-pointer text-[13px] text-td-text">Trades ({res.trades_total}{res.open_trades ? `, ${res.open_trades} still open` : ""})</summary>
            <button className={clsx(btnCls, "my-2")} onClick={() => downloadCsv("rule_trades.csv", res.trades)}><Download className="h-4 w-4" /> CSV</button>
            <SimpleTable rows={res.trades.slice(0, 100)} cols={["ticker", "entry_date", "exit_date", "entry", "exit", "bars", "reason", "net_pct", "spy_pct"]} />
          </details>
        </div>
      )}
    </div>
  );
}

function SimpleTable({ rows, cols, onSort, sort }: { rows: Record<string, unknown>[]; cols: string[]; onSort?: (c: string) => void; sort?: string }) {
  return (
    <div className="overflow-x-auto max-h-[28rem]">
      <table className="w-full text-[13px]">
        <thead className="sticky top-0 bg-td-surface"><tr className="text-td-muted text-left">{cols.map((k) => <th key={k} className={clsx("py-1 pr-3 font-normal whitespace-nowrap", onSort && "cursor-pointer hover:text-td-text", sort === k && "text-td-accent")} onClick={() => onSort?.(k)}>{k}</th>)}</tr></thead>
        <tbody>{rows.map((r, i) => <tr key={i} className="border-t border-td-line">{cols.map((k) => <td key={k} className={clsx("py-1 pr-3 tabular-nums whitespace-nowrap", typeof r[k] === "number" && /pct|ret|dist|vs|rs_|mom|dd/.test(k) ? tone(r[k] as number) : "text-td-text")}>{r[k] == null ? "—" : String(r[k])}</td>)}</tr>)}</tbody>
      </table>
    </div>
  );
}

function UniversePick({ value, onChange, custom }: { value: string; onChange: (v: string) => void; custom?: boolean }) {
  return (
    <label className="text-[13px] text-td-muted inline-flex items-center gap-1">Universe
      <select className={inputCls} value={value} onChange={(e) => onChange(e.target.value)}>
        {custom ? <option value="custom">Tickers I list</option> : <option value="sp500">S&amp;P 500 members (+ETFs)</option>}
        <option value="ours">Our 125 tracked tickers</option>
      </select>
    </label>
  );
}

const OURS_NOTE = "Our tracked tickers were picked with hindsight, so results on them look better than they would on the whole market. Use the S&P 500 for backtests that count.";

function Screener({ fields, sectors, onTicker, onTest }: { fields: FieldDef[]; sectors: string[]; onTicker?: (t: string) => void; onTest: (r: Rule) => void }) {
  const [conds, setConds] = useState<Cond[]>(PRESETS[1].conds);
  const [join, setJoin] = useState<"all" | "any">("all");
  const [etfs, setEtfs] = useState(false);
  const [universe, setUniverse] = useState<"sp500" | "ours">("sp500");
  const [res, setRes] = useState<{ as_of: string; n_matches: number; universe_n: number; universe?: string; universe_requested?: number | null; columns: string[]; rows: Record<string, unknown>[] } | null>(null);
  const [sort, setSort] = useState("");
  const [desc, setDesc] = useState(true);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const run = useCallback(async (s = sort, d = desc) => {
    setErr(""); setBusy(true);
    try { setRes(await postJson("/api/research/screen", { rule: toRule(conds, join), include_etfs: etfs, universe, sort: s || null, desc: d, limit: 500 })); }
    catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  }, [conds, join, etfs, universe, sort, desc]);
  const label = (k: string) => fields.find((f) => f.name === k)?.label || k;
  return (
    <div className="space-y-3">
      <RuleBuilder fields={fields} sectors={sectors} conds={conds} setConds={setConds} join={join} setJoin={setJoin} />
      <div className="flex flex-wrap items-center gap-3">
        <UniversePick value={universe} onChange={(v) => setUniverse(v as "sp500" | "ours")} />
        {universe === "sp500" && <label className="text-[13px] text-td-muted inline-flex items-center gap-1"><input type="checkbox" checked={etfs} onChange={(e) => setEtfs(e.target.checked)} /> Include ETFs</label>}
        <button className={btnCls} onClick={() => run()} disabled={busy || !conds.length}><Play className="h-4 w-4" /> {busy ? "Screening…" : "Screen"}</button>
        <button className={btnCls} onClick={() => onTest(toRule(conds, join))} disabled={!conds.length}><FlaskConical className="h-4 w-4" /> Test this rule</button>
        {res && <button className={btnCls} onClick={() => downloadCsv(`screen_${res.as_of}.csv`, res.rows)}><Download className="h-4 w-4" /> CSV</button>}
      </div>
      {err && <p className="text-[13px] text-red-400">{err}</p>}
      {res && (
        <>
          <p className="text-[13px] text-td-muted">
            {res.n_matches} of {res.universe_n} match, close of {res.as_of}.{" "}
            {res.universe === "ours" ? `Our tracked tickers only (${res.universe_n} of ${res.universe_requested} have price history here). ` : ""}
            A watch list, not buy signals.
          </p>
          <div className="overflow-x-auto max-h-[32rem]">
            <table className="w-full text-[13px]">
              <thead className="sticky top-0 bg-td-surface"><tr className="text-td-muted text-left">
                {["ticker", "sector", ...res.columns].map((k) => (
                  <th key={k} className={clsx("py-1 pr-3 font-normal whitespace-nowrap", k !== "ticker" && k !== "sector" && "cursor-pointer hover:text-td-text", sort === k && "text-td-accent")}
                    onClick={() => { if (k === "ticker" || k === "sector") return; const d = sort === k ? !desc : true; setSort(k); setDesc(d); run(k, d); }}>
                    {k === "ticker" ? "Ticker" : k === "sector" ? "Sector" : label(k)}{sort === k ? (desc ? " ↓" : " ↑") : ""}
                  </th>
                ))}
              </tr></thead>
              <tbody>{res.rows.map((r) => (
                <tr key={String(r.ticker)} className="border-t border-td-line">
                  <td className="py-1 pr-3"><button className="text-td-accent hover:underline" onClick={() => onTicker?.(String(r.ticker))}>{String(r.ticker)}</button></td>
                  <td className="py-1 pr-3 text-td-muted whitespace-nowrap">{String(r.sector ?? "")}</td>
                  {res.columns.map((k) => <td key={k} className={clsx("py-1 pr-3 tabular-nums", /ret|dist|rs_|mom|dd|gap/.test(k) ? tone(r[k] as Num) : "text-td-text")}>{fmt(r[k] as Num, k === "price" ? 2 : 1)}</td>)}
                </tr>
              ))}</tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

interface EsResult { label: string; n_events: number; n_dates: number; days: number[]; mean: Num[]; lo: Num[]; hi: Num[]; from_day_minus1: { day: number; mean: Num; t: Num; pct_positive: Num; n: number }[]; events: Record<string, unknown>[]; note: string; warning?: string; message?: string }

function EventStudy({ fields, sectors }: { fields: FieldDef[]; sectors: string[] }) {
  const [source, setSource] = useState("earnings");
  const [conds, setConds] = useState<Cond[]>([c("gap_pct", "<", "-5")]);
  const [join, setJoin] = useState<"all" | "any">("all");
  const [tickers, setTickers] = useState("AAPL, MSFT, NVDA, AMZN, GOOGL, META, JPM, BAC, XOM, UNH");
  const [universe, setUniverse] = useState<"custom" | "ours">("custom");
  const [items, setItems] = useState<string[]>(["5.02"]);
  const [kind, setKind] = useState("beat");
  const [thr, setThr] = useState("5");
  const [release, setRelease] = useState("cpi");
  const [win, setWin] = useState({ pre: "5", post: "20" });
  const [res, setRes] = useState<EsResult | null>(null);
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const run = async () => {
    setErr(""); setRes(null);
    try {
      const tk = tickers.split(/[,\s]+/).map((s) => s.trim().toUpperCase()).filter(Boolean);
      const body = { source, rule: source === "rule" ? toRule(conds, join) : null, tickers: universe === "ours" ? null : tk, universe: source === "rule" && universe !== "ours" ? "custom" : universe, items, kind, threshold_pct: Number(thr), release, pre: Number(win.pre), post: Number(win.post) };
      setRes(await runJob<EsResult>("/api/research/event-study", body, setBusy));
    } catch (e) { setErr((e as Error).message); } finally { setBusy(""); }
  };
  const data = res?.days?.map((d, i) => ({ d, Average: res.mean[i], band: [res.lo[i], res.hi[i]] })) || [];
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2 text-[13px] text-td-muted">
        <span>Event</span>
        <select className={inputCls} value={source} onChange={(e) => setSource(e.target.value)}>
          <option value="earnings">Earnings beat / miss</option><option value="8k">SEC 8-K filing</option><option value="macro">Macro release day</option><option value="rule">A rule turns on</option>
        </select>
        <span>Days before</span><input className={clsx(inputCls, "w-14")} value={win.pre} onChange={(e) => setWin({ ...win, pre: e.target.value })} />
        <span>after</span><input className={clsx(inputCls, "w-14")} value={win.post} onChange={(e) => setWin({ ...win, post: e.target.value })} />
      </div>
      {source === "rule" && <RuleBuilder fields={fields} sectors={sectors} conds={conds} setConds={setConds} join={join} setJoin={setJoin} />}
      {source === "earnings" && (
        <div className="flex flex-wrap items-center gap-2 text-[13px] text-td-muted">
          <select className={inputCls} value={kind} onChange={(e) => setKind(e.target.value)}><option value="beat">Beat</option><option value="miss">Miss</option><option value="any">Any report</option></select>
          {kind !== "any" && <><span>by at least</span><input className={clsx(inputCls, "w-14")} value={thr} onChange={(e) => setThr(e.target.value)} /><span>% EPS surprise</span></>}
        </div>
      )}
      {source === "8k" && (
        <div className="flex flex-wrap gap-x-3 gap-y-1 text-[13px] text-td-text">
          {ITEM_CODES.map(([code, lbl]) => (
            <label key={code} className="inline-flex items-center gap-1"><input type="checkbox" checked={items.includes(code)} onChange={(e) => setItems(e.target.checked ? [...items, code] : items.filter((x) => x !== code))} />{code} {lbl}</label>
          ))}
        </div>
      )}
      {source === "macro" && (
        <select className={inputCls} value={release} onChange={(e) => setRelease(e.target.value)}><option value="cpi">CPI</option><option value="jobs">Jobs report</option><option value="ppi">PPI</option><option value="gdp">GDP</option></select>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <UniversePick value={universe} onChange={(v) => setUniverse(v as "custom" | "ours")} custom />
        {source === "rule" && universe === "custom" && <span className="text-[12px] text-td-muted">Rule studies use S&amp;P 500 members on each date.</span>}
      </div>
      {universe === "ours" && <p className="text-[12px] text-td-warn">{OURS_NOTE}</p>}
      {source !== "rule" && universe === "custom" && (
        <label className="flex flex-col gap-1 text-[13px] text-td-muted">Tickers{source === "macro" ? " (blank = SPY)" : " (up to 130)"}
          <input className={inputCls} value={tickers} onChange={(e) => setTickers(e.target.value)} />
        </label>
      )}
      <button className={btnCls} onClick={run} disabled={!!busy}><Play className="h-4 w-4" /> {busy || "Run study"}</button>
      {err && <p className="text-[13px] text-red-400">{err}</p>}
      {res && (res.n_events === 0 ? <p className="text-[13px] text-td-muted">{res.message || "No events found."}</p> : (
        <div className="space-y-3">
          <p className="text-[13px] text-td-text">{res.label}: {res.n_events} events on {res.n_dates} dates{res.warning ? ` · ${res.warning}` : ""}</p>
          <div className="h-60">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={data}>
                <CartesianGrid stroke="#334155" strokeDasharray="3 3" />
                <XAxis dataKey="d" tick={{ fontSize: 11, fill: "#94a3b8" }} />
                <YAxis tick={{ fontSize: 11, fill: "#94a3b8" }} unit="%" />
                <Tooltip contentStyle={{ backgroundColor: "#1e293b", border: "1px solid #334155", borderRadius: 8 }} />
                <ReferenceLine x={0} stroke="#64748b" /><ReferenceLine y={0} stroke="#64748b" />
                <Area dataKey="band" stroke="none" fill="#38bdf8" fillOpacity={0.15} name="95% band" />
                <Line dataKey="Average" stroke="#38bdf8" dot={false} strokeWidth={2} name="Avg move vs SPY" />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
          <SimpleTable rows={res.from_day_minus1.map((r) => ({ "through day": r.day, "avg vs SPY %": r.mean, "t-stat": r.t, "% up": r.pct_positive, events: r.n }))} cols={["through day", "avg vs SPY %", "t-stat", "% up", "events"]} />
          <p className="text-[11px] text-td-muted">{res.note} Events on the same date count once in the t-stat. |t| under 3 is likely noise.</p>
          <button className={btnCls} onClick={() => downloadCsv("event_study_events.csv", res.events)}><Download className="h-4 w-4" /> Events CSV</button>
        </div>
      ))}
    </div>
  );
}

interface RunRow { id: string; ts: number; label?: string; rule: Rule; rule_text: string; params: Record<string, unknown>; family_runs: number; approved?: boolean; oos: Stats; promotion: { passes?: boolean; t_stat?: Num; dsr?: Num; pbo?: Num; n?: number }; portfolio: { cagr?: Num; spy_cagr?: Num } }

function History({ onLoad }: { onLoad: (r: RunRow) => void }) {
  const [runs, setRuns] = useState<RunRow[] | null>(null);
  const [err, setErr] = useState("");
  const load = useCallback(() => { fetch(apiUrl("/api/research/runs?limit=200")).then((r) => r.json()).then((j) => setRuns(j.runs || [])).catch(() => setRuns([])); }, []);
  useEffect(load, [load]);
  const toggle = async (r: RunRow) => {
    setErr("");
    const res = await fetch(apiUrl(`/api/research/runs/${r.id}/approve`), { method: r.approved ? "DELETE" : "POST" });
    if (!res.ok) setErr((await res.json().catch(() => ({}))).detail || `Error ${res.status}`);
    load();
  };
  if (!runs) return <p className="text-[13px] text-td-muted">Loading…</p>;
  if (!runs.length) return <p className="text-[13px] text-td-muted">No tests yet. Every rule test is saved here, and each retry of the same idea counts as another try.</p>;
  return (
    <div className="space-y-2">
      <button className={btnCls} onClick={() => downloadCsv("research_runs.csv", runs.map((r) => ({ when: new Date(r.ts * 1000).toISOString(), name: r.label, rule: r.rule_text, ...r.params, oos_n: r.oos?.n, oos_avg: r.oos?.mean, oos_win: r.oos?.win_rate, t: r.promotion?.t_stat, dsr: r.promotion?.dsr, pbo: r.promotion?.pbo, passes: r.promotion?.passes })))}><Download className="h-4 w-4" /> CSV</button>
      <p className="text-[12px] text-td-muted">Every saved rule shows as a badge on Best setups when it is on for a ticker. Only rules that clear the bar can be approved, and only approved rules move a pick up the Best setups list. Entry gates, stops and BUY/HOLD/SELL never change.</p>
      {err && <p className="text-[13px] text-red-400">{err}</p>}
      <div className="overflow-x-auto">
        <table className="w-full text-[13px]">
          <thead><tr className="text-td-muted text-left">{["When", "Rule", "Hold/stop", "After split: trades, avg, win", "t", "DSR", "Tries", "Bar", ""].map((h) => <th key={h} className="py-1 pr-3 font-normal">{h}</th>)}</tr></thead>
          <tbody>{runs.map((r) => (
            <tr key={r.id} className="border-t border-td-line align-top">
              <td className="py-1 pr-3 text-td-muted whitespace-nowrap">{new Date(r.ts * 1000).toLocaleDateString()}</td>
              <td className="py-1 pr-3 text-td-text">{r.label ? <b>{r.label}: </b> : null}{r.rule_text}</td>
              <td className="py-1 pr-3 text-td-muted whitespace-nowrap">{String(r.params?.hold_days)}d / {r.params?.stop_pct ? `${r.params.stop_pct}%` : "—"}</td>
              <td className={clsx("py-1 pr-3 tabular-nums whitespace-nowrap", tone(r.oos?.mean))}>{r.oos?.n ?? 0}, {fmt(r.oos?.mean, 2, "%")}, {fmt(r.oos?.win_rate, 0, "%")}</td>
              <td className="py-1 pr-3 tabular-nums">{fmt(r.promotion?.t_stat, 2)}</td>
              <td className="py-1 pr-3 tabular-nums">{fmt(r.promotion?.dsr, 2)}</td>
              <td className="py-1 pr-3 tabular-nums">{r.family_runs}</td>
              <td className={clsx("py-1 pr-3", r.promotion?.passes ? "text-emerald-400" : "text-td-warn")}>{r.promotion?.passes ? "Clears" : "Watch"}</td>
              <td className="py-1 pr-3 whitespace-nowrap">
                <button className="text-td-accent hover:underline" onClick={() => onLoad(r)}>Open</button>
                {(r.promotion?.passes || r.approved) && (
                  <button className={clsx("ml-2 hover:underline", r.approved ? "text-emerald-400" : "text-td-accent")} onClick={() => toggle(r)}>{r.approved ? "Approved ✓ (undo)" : "Approve for Best setups"}</button>
                )}
              </td>
            </tr>
          ))}</tbody>
        </table>
      </div>
    </div>
  );
}

const TABS = [{ id: "screen", label: "Screener" }, { id: "test", label: "Test a rule" }, { id: "event", label: "Event study" }, { id: "history", label: "History" }] as const;

export function ResearchPanel({ onTickerClick }: { onTickerClick?: (t: string) => void }) {
  const { fields, sectors, status } = useFields();
  const [tab, setTab] = useState<(typeof TABS)[number]["id"]>("screen");
  const [load, setLoad] = useState<{ rule: Rule; params?: Record<string, unknown> } | null>(null);
  const m = status?.meta;
  return (
    <div className="rounded-xl border border-td-line bg-td-surface p-3 sm:p-4 space-y-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-base font-semibold text-td-text inline-flex items-center gap-2"><FlaskConical className="h-5 w-5 text-td-accent" /> Research</h2>
        <span className="text-[12px] text-td-muted">{m?.as_of ? `Daily prices ${m.start} → ${m.as_of}, ${m.n_tickers} stocks and ETFs, S&P 500 members as of each date` : status?.state === "building" ? "Building price history…" : "Price history not built yet"}</span>
      </div>
      <div className="flex flex-wrap gap-1">
        {TABS.map((t) => <button key={t.id} onClick={() => setTab(t.id)} className={clsx("rounded-md px-2.5 py-1 text-[13px]", tab === t.id ? "bg-td-accent/15 text-td-accent" : "text-td-muted hover:text-td-text")}>{t.label}</button>)}
      </div>
      {!fields.length ? <p className="text-[13px] text-td-muted">Loading fields…</p> : (
        <>
          <div className={tab === "screen" ? "" : "hidden"}><Screener fields={fields} sectors={sectors} onTicker={onTickerClick} onTest={(rule) => { setLoad({ rule }); setTab("test"); }} /></div>
          <div className={tab === "test" ? "" : "hidden"}><Tester fields={fields} sectors={sectors} initial={load} /></div>
          <div className={tab === "event" ? "" : "hidden"}><EventStudy fields={fields} sectors={sectors} /></div>
          {tab === "history" && <History onLoad={(r) => { setLoad({ rule: r.rule, params: r.params }); setTab("test"); }} />}
        </>
      )}
      <p className="text-[11px] text-td-muted">Research only: nothing here changes BUY/HOLD/SELL. {m?.excluded_bad_history?.length ? `Left out for broken price history: ${m.excluded_bad_history.join(", ")}. ` : ""}Delisted stocks that free data lacks are missing, which flatters results a little.</p>
    </div>
  );
}
