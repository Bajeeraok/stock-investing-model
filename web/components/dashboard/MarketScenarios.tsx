"use client";

export interface EventScenario {
  date: string;
  name: string;
  event_type: string;
  scenario: {
    avg_return_pct: number;
    std_pct: number;
    pct_positive: number;
    n_events: number;
    rationale: string;
  } | null;
}

export function MarketScenarios({ scenarios }: { scenarios: EventScenario[] }) {
  if (!scenarios || scenarios.length === 0) {
    return (
      <div className="rounded-xl border border-slate-700/60 bg-slate-800/30 p-6 text-center">
        <p className="text-slate-400 text-sm">No upcoming events with scenario stats.</p>
        <p className="text-slate-500 text-xs mt-1">Economic calendar events (FOMC, CPI, etc.) will show historical next-day move when available.</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <p className="text-slate-500 text-sm">
        What-if: historical next-day move for SPY around similar events (12–13y). Not a forecast.
      </p>
      <div className="overflow-x-auto [-webkit-overflow-scrolling:touch] rounded-xl border border-slate-700">
        <table className="w-full text-sm border-collapse min-w-[520px]">
          <thead>
            <tr className="text-left text-slate-400">
              <th className="sticky top-0 left-0 z-[30] min-w-[5rem] w-24 px-3 py-2.5 font-medium bg-slate-800/95 backdrop-blur-sm border-b border-r border-slate-700 shadow-[2px_0_4px_-2px_rgba(0,0,0,0.3)]">Date</th>
              <th className="sticky top-0 z-[20] px-3 py-2.5 font-medium bg-slate-800/95 backdrop-blur-sm border-b border-slate-700">Event</th>
              <th className="sticky top-0 z-[20] px-3 py-2.5 font-medium bg-slate-800/95 backdrop-blur-sm border-b border-slate-700">Type</th>
              <th className="sticky top-0 z-[20] px-3 py-2.5 font-medium bg-slate-800/95 backdrop-blur-sm border-b border-slate-700">Avg next-day %</th>
              <th className="sticky top-0 z-[20] px-3 py-2.5 font-medium bg-slate-800/95 backdrop-blur-sm border-b border-slate-700">σ</th>
              <th className="sticky top-0 z-[20] px-3 py-2.5 font-medium bg-slate-800/95 backdrop-blur-sm border-b border-slate-700">% positive</th>
              <th className="sticky top-0 z-[20] px-3 py-2.5 font-medium bg-slate-800/95 backdrop-blur-sm border-b border-slate-700">N</th>
            </tr>
          </thead>
          <tbody>
            {scenarios.map((s, i) => (
              <tr key={`${s.date}-${i}`} className="group border-t border-slate-700/50 hover:bg-slate-800/30">
                <td className="sticky left-0 z-[10] min-w-[5rem] w-24 px-3 py-2.5 text-slate-300 border-r border-slate-700/70 bg-slate-900 shadow-[2px_0_4px_-2px_rgba(0,0,0,0.2)] group-hover:bg-slate-800/30">{s.date}</td>
                <td className="px-3 py-2.5 text-slate-300 max-w-[200px] truncate" title={s.name}>{s.name}</td>
                <td className="px-3 py-2.5 text-slate-400">{s.event_type}</td>
                {s.scenario ? (
                  <>
                    <td className="px-3 py-2.5 text-emerald-400">{s.scenario.avg_return_pct >= 0 ? "+" : ""}{s.scenario.avg_return_pct}%</td>
                    <td className="px-3 py-2.5 text-slate-400">±{s.scenario.std_pct}%</td>
                    <td className="px-3 py-2.5 text-slate-400">{s.scenario.pct_positive}%</td>
                    <td className="px-3 py-2.5 text-slate-500">{s.scenario.n_events}</td>
                  </>
                ) : (
                  <td colSpan={4} className="px-3 py-2.5 text-slate-500">—</td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {scenarios.some((s) => s.scenario?.rationale) && (
        <p className="text-slate-500 text-xs" title={scenarios.find((s) => s.scenario?.rationale)?.scenario?.rationale}>
          {scenarios.find((s) => s.scenario?.rationale)?.scenario?.rationale}
        </p>
      )}
    </div>
  );
}
