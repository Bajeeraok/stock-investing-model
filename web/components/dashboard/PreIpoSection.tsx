"use client";

import { clsx } from "clsx";

export interface PreIpoProxySignal {
  ticker: string;
  close?: number | null;
  composite_buy?: number | null;
  regime?: string | null;
  signal?: string | null;
}

export interface PreIpoHeadline {
  title: string;
  url?: string | null;
  published_at?: string | null;
  source?: string | null;
}

export interface PreIpoNewsBlock {
  available?: boolean;
  headline_count?: number;
  sentiment_label?: string | null;
  sentiment_score_avg?: number | null;
  sentiment_method?: string | null;
  latest?: PreIpoHeadline | null;
  headlines?: PreIpoHeadline[];
  themes?: string[];
  catalyst?: {
    headline_summary?: string | null;
    top_event_type?: string | null;
    top_impact?: number | null;
    hours_since_catalyst?: number | null;
  } | null;
  sources_note?: string | null;
  message?: string | null;
}

export interface PreIpoItem {
  id: string;
  name: string;
  sector?: string | null;
  last_valuation_usd_b?: number | null;
  valuation_as_of?: string | null;
  status?: string | null;
  note?: string | null;
  public_proxies?: string[];
  proxy_signals?: PreIpoProxySignal[];
  news?: PreIpoNewsBlock | null;
}

export interface PreIpoPanel {
  enabled?: boolean;
  disclaimer?: string | null;
  items?: PreIpoItem[];
}

function formatValuation(usdB: number | null | undefined): string {
  if (usdB == null) return "—";
  if (usdB >= 100) return `$${usdB.toFixed(0)}B`;
  return `$${usdB.toFixed(1)}B`;
}

function statusLabel(status: string | null | undefined): string {
  const s = (status || "private").toLowerCase();
  if (s === "rumored_ipo") return "Rumored IPO";
  if (s === "late_stage") return "Late stage";
  return "Private";
}

function sentimentClasses(label: string | null | undefined): string {
  const u = (label || "").toLowerCase();
  if (u.includes("bull")) return "border-emerald-500/35 text-emerald-300 bg-emerald-950/25";
  if (u.includes("bear")) return "border-red-500/35 text-red-300 bg-red-950/25";
  return "border-slate-600 text-slate-400 bg-slate-800/40";
}

function formatPubDate(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso.slice(0, 10);
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function NewsBlock({ news }: { news: PreIpoNewsBlock }) {
  if (!news.available) {
    return (
      <p className="text-[11px] text-slate-600 leading-snug pt-2 border-t border-slate-800/80">
        {news.message ?? "No matching headlines in FMP feed."}
      </p>
    );
  }

  return (
    <div className="pt-2 border-t border-slate-800/80 space-y-2">
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-[10px] uppercase tracking-wider text-slate-500">News</span>
        {news.sentiment_label && (
          <span
            className={clsx(
              "text-[9px] font-bold uppercase px-1.5 py-0.5 rounded border",
              sentimentClasses(news.sentiment_label)
            )}
          >
            {news.sentiment_label}
          </span>
        )}
        {news.headline_count != null && news.headline_count > 0 && (
          <span className="text-[10px] text-slate-600 tabular-nums">{news.headline_count} hits</span>
        )}
        {(news.themes ?? []).map((t) => (
          <span
            key={t}
            className="text-[9px] font-medium px-1.5 py-0.5 rounded bg-violet-500/10 text-violet-300 border border-violet-500/20"
          >
            {t}
          </span>
        ))}
      </div>

      {news.catalyst?.headline_summary && (
        <p className="text-[11px] text-amber-300/90 leading-snug bg-amber-950/20 border border-amber-500/20 rounded px-2 py-1">
          Catalyst: {news.catalyst.headline_summary}
        </p>
      )}

      {news.latest?.title && (
        <div className="text-xs leading-snug">
          {news.latest.url ? (
            <a
              href={news.latest.url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-slate-200 hover:text-violet-300 underline-offset-2 hover:underline"
            >
              {news.latest.title}
            </a>
          ) : (
            <span className="text-slate-200">{news.latest.title}</span>
          )}
          <p className="text-[10px] text-slate-500 mt-0.5">
            {[formatPubDate(news.latest.published_at), news.latest.source].filter(Boolean).join(" · ")}
          </p>
        </div>
      )}

      {(news.headlines?.length ?? 0) > 1 && (
        <ul className="space-y-1">
          {news.headlines!.slice(1, 4).map((h, i) => (
            <li key={`${h.title}-${i}`} className="text-[11px] text-slate-500 leading-snug truncate">
              {h.url ? (
                <a href={h.url} target="_blank" rel="noopener noreferrer" className="hover:text-slate-300">
                  {h.title}
                </a>
              ) : (
                h.title
              )}
            </li>
          ))}
        </ul>
      )}

      {news.sources_note && (
        <p className="text-[10px] text-slate-600">Source: {news.sources_note}</p>
      )}
    </div>
  );
}

export function PreIpoSection({
  panel,
  onTickerClick,
}: {
  panel?: PreIpoPanel | null;
  onTickerClick?: (ticker: string) => void;
}) {
  const items = panel?.items ?? [];
  if (!panel?.enabled || items.length === 0) return null;

  return (
    <div className="rounded-xl border border-violet-500/25 bg-violet-950/10 p-5 min-w-0">
      <h3 className="text-sm font-semibold text-slate-400 mb-1 flex items-center gap-2">
        <span className="text-violet-300">Pre-IPO watch</span>
        <span className="text-slate-500 font-normal">(private — FMP news + public proxies)</span>
      </h3>
      {panel.disclaimer && (
        <p className="text-[11px] text-slate-500 mb-3 leading-snug">{panel.disclaimer}</p>
      )}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {items.map((c) => (
          <div
            key={c.id}
            className="flex flex-col gap-2 p-4 rounded-lg bg-slate-900/60 border border-violet-500/15 min-w-0"
          >
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="font-semibold text-slate-100">{c.name}</p>
                {c.sector && <p className="text-xs text-slate-500 mt-0.5">{c.sector}</p>}
              </div>
              <span className="shrink-0 px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wide bg-violet-500/15 text-violet-300 border border-violet-500/25">
                {statusLabel(c.status)}
              </span>
            </div>
            <div className="text-sm">
              <span className="text-slate-500">Last known val </span>
              <span className="font-mono font-medium text-violet-200">
                {formatValuation(c.last_valuation_usd_b)}
              </span>
              {c.valuation_as_of && (
                <span className="text-slate-500 text-xs ml-1">({c.valuation_as_of})</span>
              )}
            </div>
            {c.note && (
              <p className="text-xs text-slate-400 leading-snug">{c.note}</p>
            )}
            {c.news && <NewsBlock news={c.news} />}
            {(c.proxy_signals?.length ?? 0) > 0 ? (
              <div className="pt-2 border-t border-slate-800/80">
                <p className="text-[10px] uppercase tracking-wider text-slate-500 mb-1.5">Public proxies</p>
                <div className="flex flex-wrap gap-1.5">
                  {c.proxy_signals!.map((p) => (
                    <button
                      key={p.ticker}
                      type="button"
                      onClick={() => onTickerClick?.(p.ticker)}
                      className={clsx(
                        "inline-flex items-center gap-1.5 px-2 py-1 rounded border text-xs",
                        onTickerClick
                          ? "border-slate-600 hover:border-emerald-500/40 hover:bg-emerald-950/20 cursor-pointer"
                          : "border-slate-700 cursor-default"
                      )}
                      title={
                        p.composite_buy != null
                          ? `${p.ticker} · score ${p.composite_buy.toFixed(0)} · ${p.regime ?? "—"}`
                          : p.ticker
                      }
                    >
                      <span className="font-mono text-emerald-400/90">{p.ticker}</span>
                      {p.composite_buy != null && (
                        <span className="text-slate-400 tabular-nums">{Math.round(p.composite_buy)}</span>
                      )}
                      {p.regime && (
                        <span
                          className={clsx(
                            "text-[9px] font-bold uppercase",
                            p.regime === "UP" && "text-emerald-400",
                            p.regime === "DOWN" && "text-red-400",
                            p.regime === "NEUTRAL" && "text-slate-500"
                          )}
                        >
                          {p.regime}
                        </span>
                      )}
                    </button>
                  ))}
                </div>
              </div>
            ) : (c.public_proxies?.length ?? 0) > 0 ? (
              <p className="text-[11px] text-slate-600">
                Proxies: {c.public_proxies!.join(", ")} (not in today&apos;s signal universe)
              </p>
            ) : null}
          </div>
        ))}
      </div>
    </div>
  );
}
