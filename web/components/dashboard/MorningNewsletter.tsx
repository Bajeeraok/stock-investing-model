"use client";

import { Mail } from "lucide-react";

export interface MorningNewsletterData {
  headline: string;
  date: string;
  sections: Array<{ title: string; items: string[] }>;
  action_items: string[];
}

interface Props {
  data: MorningNewsletterData | null | undefined;
}

export function MorningNewsletter({ data }: Props) {
  if (!data?.sections?.length && !data?.action_items?.length) {
    return null;
  }

  return (
    <article className="rounded-xl border border-slate-600 bg-slate-900/50 overflow-hidden">
      <header className="px-4 py-3 border-b border-slate-700 bg-slate-800/50 flex items-center gap-2">
        <Mail className="h-5 w-5 text-amber-400 shrink-0" />
        <h2 className="font-semibold text-slate-200">{data.headline}</h2>
      </header>
      <div className="p-4 space-y-4">
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
