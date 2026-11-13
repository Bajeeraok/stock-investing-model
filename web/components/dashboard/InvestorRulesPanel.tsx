"use client";

import { useEffect, useState } from "react";
import { clsx } from "clsx";
import { BookOpen, ChevronDown, ChevronRight } from "lucide-react";
import { apiUrl } from "@/lib/apiBase";

type Applied = "in_model" | "highlight" | "habit";
interface RuleHit {
  ticker: string;
  detail: string;
  since?: string;
  new?: boolean;
}
interface Rule {
  id: string;
  group: string;
  who: string;
  rule: string;
  applied: Applied;
  how: string;
  evidence?: string;
  live: boolean;
  hits: RuleHit[];
  hit_count: number;
  new_count: number;
}
interface RulesPayload {
  groups: { id: string; label: string }[];
  rules: Rule[];
  n_tickers: number;
  new_total: number;
  signals_as_of?: string | null;
}
export interface TickerRuleHit {
  id: string;
  group: string;
  who: string;
  rule: string;
  applied: Applied;
  detail: string;
  new?: boolean;
}

const APPLIED: Record<Applied, { label: string; cls: string }> = {
  in_model: { label: "In the model", cls: "bg-td-accent/15 text-td-accent border-td-accent/30" },
  highlight: { label: "Highlight only", cls: "bg-td-warn/15 text-td-warn border-td-warn/30" },
  habit: { label: "Your habit", cls: "bg-td-surface2 text-td-muted border-td-line" },
};

const GROUP_TONE: Record<string, string> = {
  buy: "text-td-accent",
  risk: "text-td-warn",
  trim: "text-td-warn",
  market: "text-td-info",
  habit: "text-td-muted",
};

function AppliedPill({ applied }: { applied: Applied }) {
  const a = APPLIED[applied];
  return <span className={clsx("rounded-full border px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide", a.cls)}>{a.label}</span>;
}

const SHOW = 12;

function RuleCard({ r, onTickerClick }: { r: Rule; onTickerClick?: (t: string) => void }) {
  const [all, setAll] = useState(false);
  const [why, setWhy] = useState(false);
  const hits = all ? r.hits : r.hits.slice(0, SHOW);
  return (
    <div className="rounded-lg border border-td-line bg-td-surface px-3 py-2.5 space-y-1.5">
      <div className="flex flex-wrap items-center gap-2">
        <AppliedPill applied={r.applied} />
        {r.live && (
          <span className={clsx("text-[12px] font-semibold tabular-nums", r.hit_count ? "text-td-text" : "text-td-muted")}>
            {r.hit_count ? `${r.hit_count} hit${r.hit_count === 1 ? "" : "s"}` : "No hits now"}
            {r.new_count > 0 && <span className="ml-1.5 rounded bg-td-accent/15 px-1.5 py-0.5 text-[11px] text-td-accent">{r.new_count} new today</span>}
          </span>
        )}
      </div>
      <p className="text-[14px] font-semibold text-td-text leading-snug">{r.rule}</p>
      <p className="text-[12px] text-td-muted">{r.who}</p>
      <button type="button" onClick={() => setWhy((v) => !v)} className="inline-flex items-center gap-1 text-[12px] text-td-muted hover:text-td-text">
        {why ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
        How Thrive applies it
      </button>
      {why && (
        <div className="text-[13px] text-td-text/85 leading-relaxed space-y-1">
          <p>{r.how}</p>
          {r.evidence && <p className="text-td-muted">Evidence: {r.evidence}</p>}
        </div>
      )}
      {r.hits.length > 0 && (
        <div className="flex flex-wrap gap-1.5 pt-0.5">
          {hits.map((h) =>
            h.ticker === "MARKET" ? (
              <span key="m" className="rounded-md border border-td-info/30 bg-td-info/10 px-2 py-0.5 text-[12px] text-td-text">
                {h.new && <span className="mr-1 font-bold text-td-accent">NEW</span>}
                {h.detail}
              </span>
            ) : (
              <button
                key={h.ticker}
                type="button"
                title={`${h.detail}${h.since ? ` · since ${h.since}` : ""}`}
                onClick={() => onTickerClick?.(h.ticker)}
                className={clsx(
                  "rounded-md border px-2 py-0.5 text-[12px] font-semibold tabular-nums hover:border-td-accent",
                  h.new ? "border-td-accent/50 bg-td-accent/10 text-td-accent" : "border-td-line bg-td-surface2 text-td-text",
                )}
              >
                {h.ticker}
              </button>
            ),
          )}
          {r.hits.length > SHOW && (
            <button type="button" onClick={() => setAll((v) => !v)} className="text-[12px] text-td-muted hover:text-td-text">
              {all ? "Show less" : `+${r.hits.length - SHOW} more`}
            </button>
          )}
        </div>
      )}
    </div>
  );
}

interface Sp500Scan {
  as_of?: string;
  n_scanned: number;
  status?: string;
  rule_hits?: Record<string, { count: number; hits: { ticker: string; detail: string }[] }>;
  leaders?: { ticker: string; sector?: string; mom_12_1: number; rs_6m_vs_spy?: number; drawdown_52w: number }[];
  note?: string;
}

const SCAN_LABEL: Record<string, string> = {
  trend_template: "Uptrend template",
  below_200d: "Below 200-day",
  overextended: "Overextended",
  distribution: "Heavy-volume drop",
};

function Sp500ScanCard({ scan, onTickerClick }: { scan: Sp500Scan; onTickerClick?: (t: string) => void }) {
  const [open, setOpen] = useState<string | null>(null);
  if (!scan.n_scanned) return <p className="text-[13px] text-td-muted">S&P 500 scan is building. Check back in a minute.</p>;
  const sel = open && scan.rule_hits?.[open];
  return (
    <section className="space-y-2">
      <h3 className="text-[13px] font-bold uppercase tracking-wide text-td-info">S&P 500 + ETFs scan · {scan.n_scanned} tickers</h3>
      <div className="flex flex-wrap gap-1.5">
        {Object.entries(scan.rule_hits ?? {}).map(([id, v]) => (
          <button
            key={id}
            type="button"
            onClick={() => setOpen(open === id ? null : id)}
            className={clsx("rounded-md border px-2 py-1 text-[12px] tabular-nums", open === id ? "border-td-accent text-td-accent" : "border-td-line text-td-text")}
          >
            {SCAN_LABEL[id] ?? id}: <span className="font-semibold">{v.count}</span>
          </button>
        ))}
      </div>
      {sel && (
        <div className="flex flex-wrap gap-1">
          {sel.hits.map((h) => (
            <button key={h.ticker} type="button" title={h.detail} onClick={() => onTickerClick?.(h.ticker)} className="rounded border border-td-line bg-td-surface2 px-1.5 py-0.5 text-[11px] font-semibold hover:border-td-accent">
              {h.ticker}
            </button>
          ))}
        </div>
      )}
      {!!scan.leaders?.length && (
        <div className="rounded-lg border border-td-line bg-td-surface px-3 py-2.5 space-y-1.5">
          <div className="flex flex-wrap items-center gap-2">
            <AppliedPill applied="highlight" />
            <p className="text-[14px] font-semibold text-td-text">Momentum leaders (watch list)</p>
          </div>
          <p className="text-[12px] text-td-muted">O'Neil · Jegadeesh & Titman. {scan.note}</p>
          <div className="flex flex-wrap gap-1.5">
            {scan.leaders.map((l) => (
              <button key={l.ticker} type="button" onClick={() => onTickerClick?.(l.ticker)} title={`${l.sector ?? ""} · ${l.drawdown_52w}% off high`} className="rounded-md border border-td-line bg-td-surface2 px-2 py-0.5 text-[12px] tabular-nums hover:border-td-accent">
                <span className="font-semibold text-td-text">{l.ticker}</span> <span className="text-td-accent">{l.mom_12_1 > 0 ? "+" : ""}{l.mom_12_1.toFixed(0)}%</span>
              </button>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

export function InvestorRulesPanel({ onTickerClick }: { onTickerClick?: (t: string) => void }) {
  const [scan, setScan] = useState<Sp500Scan | null>(null);
  useEffect(() => {
    fetch(apiUrl("/api/investor-rules/sp500"))
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => j && setScan(j))
      .catch(() => {});
  }, []);
  const [data, setData] = useState<RulesPayload | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    fetch(apiUrl("/api/investor-rules"))
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((j) => alive && setData(j))
      .catch((e) => alive && setErr(e instanceof Error ? e.message : "Failed"));
    return () => {
      alive = false;
    };
  }, []);
  if (err) return <p className="text-sm text-td-warn">Investor rules unavailable: {err}</p>;
  if (!data) return <p className="text-sm text-td-muted">Loading investor rules…</p>;
  return (
    <div className="space-y-5">
      <div className="rounded-lg border border-td-line bg-td-surface2/50 px-3 py-2.5 space-y-1.5">
        <div className="flex items-center gap-2">
          <BookOpen className="h-4 w-4 text-td-accent" aria-hidden />
          <p className="text-[14px] font-semibold text-td-text">Rules from well-known investors, checked live on {data.n_tickers} tickers</p>
        </div>
        <p className="text-[13px] text-td-muted leading-relaxed">
          <AppliedPill applied="in_model" /> already drives gates, stops or caps. <AppliedPill applied="highlight" /> is a flag only and never changes
          BUY/HOLD/SELL until it passes a backtest. <AppliedPill applied="habit" /> is a process rule for you.
          {data.new_total > 0 && <> {data.new_total} hits are new today.</>}
        </p>
      </div>
      {data.groups.map((g) => {
        const rules = data.rules.filter((r) => r.group === g.id);
        if (!rules.length) return null;
        return (
          <section key={g.id} className="space-y-2">
            <h3 className={clsx("text-[13px] font-bold uppercase tracking-wide", GROUP_TONE[g.id])}>{g.label}</h3>
            <div className="grid gap-2 md:grid-cols-2">
              {rules.map((r) => (
                <RuleCard key={r.id} r={r} onTickerClick={onTickerClick} />
              ))}
            </div>
          </section>
        );
      })}
      {scan && <Sp500ScanCard scan={scan} onTickerClick={onTickerClick} />}
      <p className="text-[12px] text-td-muted">Education, not personal advice. Rules are paraphrased from each investor's public writing and interviews.</p>
    </div>
  );
}

/** Compact "Investor rules hit" line for a ticker's Verdict tab. */
export function TickerInvestorRules({ ticker }: { ticker: string }) {
  const [hits, setHits] = useState<TickerRuleHit[] | null>(null);
  useEffect(() => {
    let alive = true;
    fetch(apiUrl(`/api/investor-rules?ticker=${encodeURIComponent(ticker)}`))
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => alive && setHits(j?.hits ?? []))
      .catch(() => alive && setHits([]));
    return () => {
      alive = false;
    };
  }, [ticker]);
  if (!hits?.length) return null;
  return (
    <div className="rounded-lg border border-td-line bg-td-surface px-3 py-2 space-y-1.5">
      <div className="flex items-center gap-2">
        <BookOpen className="h-4 w-4 shrink-0 text-td-accent" aria-hidden />
        <p className="text-[13px] font-semibold uppercase tracking-wide text-td-text">Investor rules hit</p>
      </div>
      <ul className="space-y-1">
        {hits.map((h) => (
          <li key={h.id} className="text-[13px] leading-snug">
            <span className={clsx("font-semibold", GROUP_TONE[h.group])}>{h.rule}</span>{" "}
            <span className="text-td-muted">
              {h.detail} · {h.who.split(" · ")[0]} · {APPLIED[h.applied].label}
              {h.new && <span className="ml-1 font-bold text-td-accent">NEW</span>}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
