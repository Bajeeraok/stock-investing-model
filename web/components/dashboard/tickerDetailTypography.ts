/** Shared readable typography for ticker modal — avoid disclaimer-sized micro copy for body text. */
export const TD = {
  sectionLabel: "text-xs font-semibold uppercase tracking-wide text-slate-300",
  sectionTitle: "text-sm font-semibold text-slate-100",
  body: "text-sm text-slate-200 leading-relaxed",
  bodyMuted: "text-sm text-slate-400 leading-relaxed",
  footnote: "text-xs text-slate-500 leading-snug",
  card: "rounded-xl border border-slate-600/50 bg-slate-800/40 px-4 py-3",
  summaryCard: "rounded-xl border border-slate-600/50 bg-slate-800/60 px-4 py-3.5",
} as const;
