/**
 * Maps backend retail visual_status tokens to Tailwind classes.
 * Backend is source of truth; React only applies styling.
 */

export type RetailVisualStatus =
  | "cleared"
  | "blocked"
  | "bull"
  | "stormy"
  | "hot"
  | "marginal"
  | "neutral"
  | "balanced"
  | "tight"
  | "favorable"
  | "oversold";

export type RetailStatusStyle = {
  bg: string;
  text: string;
  border: string;
  badge?: string;
};

/** Terracotta / orange for blocked, hot, stormy; emerald for cleared / bull. */
export const RETAIL_STATUS_STYLES: Record<string, RetailStatusStyle> = {
  cleared: {
    bg: "bg-emerald-950/40",
    text: "text-emerald-400",
    border: "border-emerald-800",
    badge: "bg-emerald-500/15 text-emerald-300 border-emerald-500/45",
  },
  bull: {
    bg: "bg-emerald-950/40",
    text: "text-emerald-400",
    border: "border-emerald-800",
    badge: "bg-emerald-500/15 text-emerald-300 border-emerald-500/45",
  },
  favorable: {
    bg: "bg-emerald-950/40",
    text: "text-emerald-400",
    border: "border-emerald-800",
  },
  blocked: {
    bg: "bg-orange-950/40",
    text: "text-orange-400",
    border: "border-orange-800",
    badge: "bg-orange-500/15 text-orange-300 border-orange-800/60",
  },
  stormy: {
    bg: "bg-orange-950/40",
    text: "text-orange-400",
    border: "border-orange-800",
    badge: "bg-orange-500/15 text-orange-300 border-orange-800/60",
  },
  hot: {
    bg: "bg-orange-950/40",
    text: "text-orange-400",
    border: "border-orange-800",
    badge: "bg-orange-500/15 text-orange-300 border-orange-800/60",
  },
  tight: {
    bg: "bg-orange-950/40",
    text: "text-orange-400",
    border: "border-orange-800",
  },
  neutral: {
    bg: "bg-slate-900/50",
    text: "text-slate-400",
    border: "border-slate-700",
    badge: "bg-slate-800/80 text-slate-300 border-slate-600",
  },
  balanced: {
    bg: "bg-slate-900/50",
    text: "text-slate-300",
    border: "border-slate-600",
  },
  oversold: {
    bg: "bg-sky-950/40",
    text: "text-sky-400",
    border: "border-sky-800",
  },
  marginal: {
    bg: "bg-amber-950/35",
    text: "text-amber-300",
    border: "border-amber-700/60",
    badge: "bg-amber-500/15 text-amber-200 border-amber-500/45",
  },
};

export function retailStatusClasses(
  status: string | null | undefined,
  part: keyof RetailStatusStyle = "badge"
): string {
  const key = (status || "neutral").toLowerCase();
  const style = RETAIL_STATUS_STYLES[key] ?? RETAIL_STATUS_STYLES.neutral;
  if (part === "badge" && style.badge) return style.badge;
  if (part === "bg") return style.bg;
  if (part === "text") return style.text;
  if (part === "border") return style.border;
  return `${style.bg} ${style.text} ${style.border}`;
}

export function retailStatusRowClasses(status: string | null | undefined, pass?: boolean): string {
  const visual = status ?? (pass ? "cleared" : "blocked");
  const s = RETAIL_STATUS_STYLES[visual] ?? (pass ? RETAIL_STATUS_STYLES.cleared : RETAIL_STATUS_STYLES.blocked);
  return `${s.bg} ${s.border}`;
}
