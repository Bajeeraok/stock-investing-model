"use client";

import { Info, Mail } from "lucide-react";

export interface MorningNewsletterData {
  headline: string;
  date: string;
  /** Human-readable ET timestamp for display */
  date_display?: string;
  /** Reconciled quadrant when available — aligns with hero panel */
  quadrant?: string | null;
  /** Same unified read as RetailMarketDecisionsPanel hero — avoids contradicting three-line brief */
  master_context?: {
    quadrant?: string | null;
    primary_message?: string | null;
    explanation?: string | null;
    coexistence_note?: string | null;
    temperature_label?: string | null;
    regime_label?: string | null;
    hmm_bull_pct?: number | null;
  } | null;
  /** Regime → portfolio → key level (compressed UX) */
  three_line_brief?: string[];
  sections: Array<{ title: string; items: string[] }>;
  action_items: string[];
  /** Inline hold vs trim guidance — self-contained in morning brief */
  hold_vs_trade_teaser?: string;
  hold_vs_trade_more?: string | null;
}

interface Props {
  data: MorningNewsletterData | null | undefined;
}

export function MorningNewsletter({ data }: Props) {
  if (
    !data?.sections?.length &&
    !data?.action_items?.length &&
    !data?.three_line_brief?.length &&
    !data?.hold_vs_trade_teaser &&
    !data?.hold_vs_trade_more
  ) {
    return null;
  }

  return (
    <article className="rounded-xl border border-slate-600 bg-slate-900/50 overflow-hidden">
      <header className="px-4 py-3 border-b border-slate-700 bg-slate-800/50 flex items-center gap-2">
        <Mail className="h-5 w-5 text-amber-400 shrink-0" />
        <h2 className="font-semibold text-slate-200">{data.headline}</h2>
      </header>
      <div className="p-4 space-y-4">
        {data.master_context?.primary_message && (
          <section className="rounded-lg border border-emerald-500/30 bg-emerald-950/20 p-4 space-y-2">
            <p className="text-sm font-semibold text-emerald-200">{data.master_context.primary_message}</p>
            {data.master_context.explanation && (
              <p className="text-sm text-slate-300 leading-snug">{data.master_context.explanation}</p>
            )}
            <div className="flex flex-wrap gap-2 text-[11px]">
              {data.master_context.temperature_label && (
                <span className="px-2 py-0.5 rounded border border-sky-500/30 text-sky-300">
                  Short-term: {data.master_context.temperature_label}
                </span>
              )}
              {data.master_context.regime_label && (
                <span className="px-2 py-0.5 rounded border border-emerald-500/30 text-emerald-300">
                  Regime: {data.master_context.regime_label}
                  {data.master_context.hmm_bull_pct != null &&
                    ` (~${data.master_context.hmm_bull_pct}% bull)`}
                </span>
              )}
            </div>
            {data.master_context.coexistence_note && (
              <p className="text-xs text-slate-400">{data.master_context.coexistence_note}</p>
            )}
          </section>
        )}
        {data.three_line_brief && data.three_line_brief.length > 0 && (
          <section className="rounded-lg border border-amber-500/20 bg-amber-950/15 px-3 py-2.5 space-y-1.5">
            <h3 className="text-[10px] font-semibold uppercase tracking-wider text-amber-500/90">Today in 3 lines</h3>
            <ol className="list-decimal list-inside text-sm text-slate-200 space-y-1">
              {data.three_line_brief.map((line, i) => (
                <li key={i} className="leading-snug pl-1">
                  {line}
                </li>
              ))}
            </ol>
          </section>
        )}
        {(data.hold_vs_trade_teaser || data.hold_vs_trade_more) && (
          <section className="rounded-lg border border-sky-500/25 bg-sky-950/20 px-3 py-2.5 space-y-1">
            <h3 className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-sky-400/90">
              <Info className="h-3.5 w-3.5 shrink-0" aria-hidden />
              Hold or trim?
            </h3>
            {data.hold_vs_trade_teaser && (
              <p className="text-sm text-slate-300 leading-snug whitespace-pre-line">{data.hold_vs_trade_teaser}</p>
            )}
            {data.hold_vs_trade_more && (
              <p className="text-xs text-slate-500 leading-snug whitespace-pre-line">{data.hold_vs_trade_more}</p>
            )}
          </section>
        )}
        {data.sections.map((sec, i) => (
          <section key={i}>
            <h3 className="text-xs font-medium uppercase tracking-wider text-slate-500 mb-1.5">{sec.title}</h3>
            <ul className="space-y-1 text-sm text-slate-300">
              {sec.items.map((item, j) => (
                <li key={j} className="leading-snug">
                  {item}
                </li>
              ))}
            </ul>
          </section>
        ))}
        {data.action_items && data.action_items.length > 0 && (
          <section>
            <h3 className="text-xs font-medium uppercase tracking-wider text-amber-500/90 mb-1.5">Action items</h3>
            <ul className="space-y-1.5 text-sm">
              {data.action_items.map((item, j) => (
                <li key={j} className="flex items-start gap-2 text-slate-200">
                  <span className="text-amber-400 mt-0.5">•</span>
                  <span className="leading-snug">{item}</span>
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>
    </article>
  );
}
