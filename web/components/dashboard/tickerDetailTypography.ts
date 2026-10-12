/** Shared readable typography for the ticker-detail modal's `.td-skin` scope — avoid
 * disclaimer-sized micro copy for body text. Colors/chrome use the td-* tokens (see
 * tailwind.config.ts + globals.css's `.td-skin`), matching the Thrive Alpha Redesign
 * artifact; only valid inside TickerDetailModal's subtree. */
export const TD = {
  sectionLabel: "text-xs font-semibold uppercase tracking-wide text-td-muted",
  sectionTitle: "text-sm font-semibold text-td-text",
  body: "text-sm text-td-text leading-relaxed",
  bodyMuted: "text-sm text-td-muted leading-relaxed",
  footnote: "text-xs text-td-muted/80 leading-snug",
  card: "rounded-xl border border-td-line bg-td-surface px-4 py-3",
  summaryCard: "rounded-xl border border-td-line bg-td-surface2 px-4 py-3.5",
} as const;
