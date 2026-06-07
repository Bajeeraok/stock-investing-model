"use client";

/** Shared empty / loading / error shell for Analysis tab sections (always visible toggles). */
export function AnalysisSectionEmpty({
  loading,
  title,
  message,
  hints,
}: {
  loading?: boolean;
  title?: string;
  message: string;
  hints?: readonly string[];
}) {
  return (
    <div className="rounded-lg border border-slate-600/80 bg-slate-800/30 p-4 space-y-2">
      {loading ? (
        <p className="text-sm text-slate-400 animate-pulse">Loading…</p>
      ) : (
        <>
          {title ? <p className="text-sm font-medium text-slate-300">{title}</p> : null}
          <p className="text-sm text-slate-500 leading-relaxed">{message}</p>
          {hints && hints.length > 0 ? (
            <ul className="text-xs text-slate-500 list-disc pl-4 space-y-1 mt-2">
              {hints.map((h) => (
                <li key={h}>{h}</li>
              ))}
            </ul>
          ) : null}
        </>
      )}
    </div>
  );
}

export const ANALYSIS_LOAD_HINTS = {
  bundle: [
    "Click Refresh on the dashboard (top right) to populate the server cache.",
    "Then reopen Analysis — data loads from /api/dashboard/analysis-bundle.",
  ],
  audit100: [
    "100-ticker cohort is logged on run_daily / EOD cron (not dashboard refresh alone).",
    "Mount DATA_ROOT on Railway so signal_audit.db survives redeploys.",
    "Config: signal_audit.enabled and config/signal_audit_cohort.yaml.",
  ],
  forward: [
    "Need at least 2 saved EOD snapshots (Save EOD button or daily cron).",
    "Tracks your watchlist + portfolio tickers, not the 100-ticker audit cohort.",
  ],
  paper: [
    "Logs on dashboard Refresh when signals pass all 4 gates (GO) and are actionable.",
    "Paper CSV lives under DATA_ROOT — use a persistent volume on Railway.",
    "Full summary unlocks after min_completed_for_summary completed trades (default 60).",
  ],
} as const;
