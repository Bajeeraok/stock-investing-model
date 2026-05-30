"use client";

import { useState } from "react";
import {
  Calendar,
  GitBranch,
  RotateCw,
  Target,
  TrendingUp,
} from "lucide-react";
import type { RetailMarketDecisions } from "./RetailMarketDecisionsPanel";

export function RetailMarketDecisionsDeepDive({
  data,
  macroBackdrop,
}: {
  data: RetailMarketDecisions;
  macroBackdrop?: { bullets?: string[]; disclaimer?: string } | null;
}) {
  const [contextExpanded, setContextExpanded] = useState(false);
  const [macroExpanded, setMacroExpanded] = useState(false);

  const macroBullets = (macroBackdrop?.bullets ?? []).filter(
    (b) => !b.startsWith("Unified read:") && !b.startsWith("Long-term SPY regime:"),
  );

  const scenarios = data.if_then_scenarios ?? [];
  const questions = data.five_questions ?? [];
  const checklist = data.morning_checklist ?? [];
  const overnight = data.overnight_delta;
  const breadth = data.breadth_panel;
  const crowd = data.crowd_positioning;
  const earningsPulse = data.earnings_season_pulse;
  const triggers = data.trigger_levels;
  const rotation = data.sector_rotation;
  const credit = data.credit_pulse;
  const personalEarnings = data.personal_earnings_calendar;
  const hasContextPillars = Boolean(
    crowd || earningsPulse || triggers || rotation || breadth || credit || personalEarnings,
  );

  return (
    <div className="space-y-4">
      {overnight?.summary && (
        <div className="rounded-lg border border-slate-600/70 bg-slate-800/40 px-3 py-2">
          <p className="text-xs font-medium text-slate-300 uppercase tracking-wider mb-1">Overnight</p>
          <p className="text-sm text-slate-100">{overnight.summary}</p>
          {(overnight.lines ?? []).map((l) => (
            <p key={l.text} className="text-xs text-slate-300 mt-0.5">
              {l.text}
            </p>
          ))}
        </div>
      )}

      {checklist.length > 0 && (
        <div className="rounded-lg border border-slate-600/70 bg-slate-800/40 px-3 py-2">
          <p className="text-xs font-medium text-slate-300 uppercase tracking-wider mb-2">Today&apos;s checklist</p>
          <ul className="space-y-1.5">
            {checklist.map((c, i) => (
              <li key={i} className="text-sm flex gap-2">
                <span className="text-slate-400 shrink-0 text-xs font-mono min-w-[5.5rem]">{c.time}</span>
                <span className="text-slate-100">{c.task}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {questions.length > 0 && (
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-slate-300 mb-2">Five questions</p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            {questions.map((q) => (
              <div key={q.question} className="rounded-lg border border-slate-600/70 bg-slate-800/40 px-3 py-2">
                <p className="text-xs font-medium text-slate-300">{q.question}</p>
                <p className="text-sm text-slate-100 mt-0.5 leading-snug whitespace-pre-line">{q.answer}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {data.hold_vs_trade?.answer && (
        <div className="rounded-lg border border-sky-500/30 bg-sky-950/25 px-4 py-3">
          <p className="text-xs font-semibold uppercase tracking-wider text-sky-200 mb-1">
            {data.hold_vs_trade.headline ?? "Hold vs tactical trim"}
          </p>
          <p className="text-sm text-slate-100 leading-snug">{data.hold_vs_trade.answer}</p>
          {(data.hold_vs_trade.bullets ?? []).map((b) => (
            <p key={b} className="text-sm text-slate-200 mt-1 flex gap-2">
              <span className="text-sky-400 shrink-0">→</span>
              {b}
            </p>
          ))}
        </div>
      )}

      {scenarios.length > 0 && (
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-slate-300 mb-2 flex items-center gap-1">
            <GitBranch className="h-3.5 w-3.5" /> Key scenarios
          </p>
          <ul className="space-y-2">
            {scenarios.map((s, i) => (
              <li key={i} className="rounded-lg border border-violet-500/25 bg-violet-950/15 px-3 py-2">
                <p className="text-sm font-medium text-violet-100">IF {s.condition}</p>
                {s.impact && <p className="text-xs text-slate-300 mt-0.5">→ {s.impact}</p>}
                {s.action && <p className="text-xs text-emerald-200 mt-1">Action: {s.action}</p>}
              </li>
            ))}
          </ul>
        </div>
      )}

      {(data.portfolio_risk?.adjustments ?? []).length > 0 && (
        <ul className="text-xs text-amber-100/90 list-disc list-inside space-y-1">
          {data.portfolio_risk!.adjustments!.map((a, i) => (
            <li key={i}>{a}</li>
          ))}
        </ul>
      )}
      {(data.portfolio_risk?.do_nothing_if ?? []).length > 0 && (
        <p className="text-xs text-slate-300 flex items-start gap-1">
          <TrendingUp className="h-3 w-3 shrink-0 mt-0.5" />
          Do nothing if: {data.portfolio_risk!.do_nothing_if!.join("; ")}
        </p>
      )}

      {hasContextPillars && (
        <div className="space-y-2">
          <p className="text-xs font-semibold uppercase tracking-wider text-slate-300 flex items-center gap-1">
            <RotateCw className="h-3.5 w-3.5" /> Context pillars
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
            {breadth?.plain_english && (
              <div className="rounded-lg border border-emerald-500/20 bg-emerald-950/10 px-3 py-2 text-slate-200">
                <span className="text-emerald-300 font-medium">Breadth: </span>
                {breadth.plain_english}
              </div>
            )}
            {credit?.plain_english && (
              <div className="rounded-lg border border-slate-600/60 bg-slate-800/30 px-3 py-2 text-slate-200">
                <span className="font-medium">Credit: </span>
                {credit.hy_spread_pct != null && `HY ${credit.hy_spread_pct}% — `}
                {credit.plain_english}
              </div>
            )}
            {triggers?.headline && (
              <div className="rounded-lg border border-sky-500/20 bg-sky-950/15 px-3 py-2 text-slate-200">
                <Target className="h-3.5 w-3.5 inline mr-1 text-sky-400" />
                {triggers.headline}
              </div>
            )}
            {rotation?.plain_english && (
              <div className="rounded-lg border border-slate-600/60 bg-slate-800/30 px-3 py-2 text-slate-200">
                {rotation.plain_english}
              </div>
            )}
            {crowd?.fear_greed?.score != null && (
              <div className="rounded-lg border border-slate-600/60 bg-slate-800/30 px-3 py-2 text-slate-200">
                Fear & Greed {crowd.fear_greed.score}
                {crowd.fear_greed.rating ? ` (${crowd.fear_greed.rating})` : ""}
              </div>
            )}
            {crowd?.spy_put_call?.ratio != null && (
              <div className="rounded-lg border border-violet-500/20 bg-violet-950/10 px-3 py-2 text-slate-200">
                {crowd.spy_put_call.plain_english ?? `Put/Call ${crowd.spy_put_call.ratio}`}
              </div>
            )}
            {earningsPulse?.phase && (
              <div className="rounded-lg border border-slate-600/60 bg-slate-800/30 px-3 py-2 text-slate-200">
                Earnings {earningsPulse.phase}: {earningsPulse.plain_english}
              </div>
            )}
          </div>
          <button
            type="button"
            onClick={() => setContextExpanded((o) => !o)}
            className="text-xs text-slate-300 hover:text-slate-100"
          >
            {contextExpanded ? "Less" : "More"} pillar detail
          </button>
          {contextExpanded && (
            <div className="mt-2 space-y-2 text-xs text-slate-300">
              {crowd?.aaii?.note && <p>{crowd.aaii.note}</p>}
              {triggers?.tech_rule && <p>{triggers.tech_rule}</p>}
              {personalEarnings?.items?.map((it) => (
                <p key={it.ticker} className="text-amber-100/90">
                  {it.ticker} ({it.days_until}d): {it.action}
                </p>
              ))}
            </div>
          )}
        </div>
      )}

      {macroBullets.length > 0 && (
        <div>
          <button
            type="button"
            onClick={() => setMacroExpanded((o) => !o)}
            className="text-xs font-semibold uppercase tracking-wider text-slate-300 hover:text-slate-100"
          >
            Macro backdrop ({macroBullets.length})
          </button>
          {macroExpanded && (
            <ul className="mt-2 list-disc list-inside text-xs text-slate-300 space-y-1">
              {macroBullets.map((b) => (
                <li key={b}>{b}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      {data.disclaimer && <p className="text-[10px] text-slate-400">{data.disclaimer}</p>}
    </div>
  );
}
