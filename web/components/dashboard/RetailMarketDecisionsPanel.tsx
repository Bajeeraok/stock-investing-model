"use client";

import { clsx } from "clsx";
import { useState } from "react";
import { Thermometer, Grid3X3, GitBranch, HelpCircle, Shield, TrendingUp, Users, Calendar, Target, RotateCw } from "lucide-react";

export interface RetailMarketDecisions {
  five_questions?: { question: string; answer: string }[];
  market_temperature?: {
    level?: string;
    label?: string;
    vix?: number | null;
    drivers?: string[];
    interpretation?: string;
  };
  strategy_matrix?: {
    short_term?: { horizon?: string; stance?: string; action?: string; bullets?: string[] };
    medium_term?: { horizon?: string; stance?: string; action?: string; bullets?: string[] };
    long_term?: {
      horizon?: string;
      stance?: string;
      action?: string;
      bullets?: string[];
      thesis_breakers?: { label: string; triggered?: boolean }[];
    };
    grid?: { short?: string; medium?: string; long?: string };
  };
  if_then_scenarios?: {
    condition: string;
    impact?: string;
    action?: string;
    probability_pct?: number | null;
    gap_fade_note?: string;
  }[];
  portfolio_risk?: {
    score?: number;
    score_scale?: string;
    adjustments?: string[];
    do_nothing_if?: string[];
  };
  breadth_panel?: {
    proxy?: string;
    market_breadth?: string;
    plain_english?: string;
    data_note?: string;
  };
  crowd_positioning?: {
    fear_greed?: { score?: number; rating?: string; source?: string } | null;
    aaii?: { bull_pct?: number; bear_pct?: number; note?: string } | null;
    plain_english?: string;
  } | null;
  earnings_season_pulse?: {
    phase?: string;
    mood?: string;
    plain_english?: string;
    beat_rate?: { beat_pct?: number; sample_n?: number } | null;
  } | null;
  trigger_levels?: {
    headline?: string;
    tech_rule?: string;
    broad_rule?: string;
  } | null;
  sector_rotation?: {
    plain_english?: string;
    rotate_toward?: string[];
    rotate_away?: string[];
  } | null;
  personal_earnings_calendar?: {
    plain_english?: string;
    items?: { ticker: string; days_until: number; action: string }[];
  } | null;
  disclaimer?: string;
}

const TEMP_STYLE: Record<string, string> = {
  cold: "border-sky-500/40 bg-sky-950/30 text-sky-200",
  cool: "border-sky-500/30 bg-sky-950/20 text-sky-300",
  warm: "border-amber-500/30 bg-amber-950/20 text-amber-200",
  warm_hot: "border-orange-500/35 bg-orange-950/25 text-orange-200",
  hot: "border-red-500/35 bg-red-950/25 text-red-200",
};

const ACTION_STYLE: Record<string, string> = {
  BUY: "bg-emerald-500/20 text-emerald-300 border-emerald-500/40",
  HOLD: "bg-slate-500/20 text-slate-300 border-slate-600",
  REDUCE: "bg-amber-500/20 text-amber-300 border-amber-500/40",
};

function ActionChip({ action }: { action?: string }) {
  if (!action) return null;
  return (
    <span className={clsx("text-xs font-semibold px-2 py-0.5 rounded border uppercase", ACTION_STYLE[action] ?? ACTION_STYLE.HOLD)}>
      {action}
    </span>
  );
}

export function RetailMarketDecisionsPanel({ data }: { data: RetailMarketDecisions | null | undefined }) {
  const [contextOpen, setContextOpen] = useState(false);

  if (!data) return null;

  const temp = data.market_temperature;
  const matrix = data.strategy_matrix;
  const scenarios = data.if_then_scenarios ?? [];
  const questions = data.five_questions ?? [];
  const risk = data.portfolio_risk;
  const breadth = data.breadth_panel;
  const crowd = data.crowd_positioning;
  const earningsPulse = data.earnings_season_pulse;
  const triggers = data.trigger_levels;
  const rotation = data.sector_rotation;
  const personalEarnings = data.personal_earnings_calendar;
  const hasContextPillars = Boolean(crowd || earningsPulse || triggers || rotation || breadth || personalEarnings);

  return (
    <div className="rounded-xl border border-emerald-500/20 bg-slate-900/60 overflow-hidden space-y-0">
      <div className="px-4 py-3 border-b border-slate-700/60 bg-slate-800/40">
        <h2 className="text-base font-semibold text-slate-100 flex items-center gap-2">
          <HelpCircle className="h-5 w-5 text-emerald-400" />
          What should I do today?
        </h2>
        <p className="text-xs text-slate-500 mt-1">Decisions first — context below. Not financial advice.</p>
      </div>

      <div className="p-4 space-y-5">
        {/* Five questions */}
        {questions.length > 0 && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            {questions.map((q) => (
              <div key={q.question} className="rounded-lg border border-slate-700/60 bg-slate-800/30 px-3 py-2">
                <p className="text-xs font-medium text-slate-400">{q.question}</p>
                <p className="text-sm text-slate-200 mt-0.5 leading-snug">{q.answer}</p>
              </div>
            ))}
          </div>
        )}

        {/* Temperature */}
        {temp && (
          <div className={clsx("rounded-lg border p-4", TEMP_STYLE[temp.level ?? "warm"] ?? TEMP_STYLE.warm)}>
            <div className="flex items-center gap-2 mb-2">
              <Thermometer className="h-4 w-4 shrink-0" />
              <span className="text-sm font-semibold uppercase tracking-wide">Market temperature: {temp.label}</span>
            </div>
            {temp.drivers && temp.drivers.length > 0 && (
              <p className="text-xs opacity-80 mb-2">{temp.drivers.join(" · ")}</p>
            )}
            <p className="text-sm leading-relaxed">{temp.interpretation}</p>
          </div>
        )}

        {/* 3×3 matrix simplified */}
        {matrix && (
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-2 flex items-center gap-1">
              <Grid3X3 className="h-3.5 w-3.5" /> Strategy matrix (ST · MT · LT)
            </p>
            <div className="overflow-x-auto">
              <table className="w-full text-sm border border-slate-700/60 rounded-lg overflow-hidden">
                <thead>
                  <tr className="bg-slate-800/60 text-slate-400 text-xs">
                    <th className="text-left px-3 py-2">Horizon</th>
                    <th className="text-left px-3 py-2">Action</th>
                    <th className="text-left px-3 py-2 hidden sm:table-cell">Guidance</th>
                  </tr>
                </thead>
                <tbody>
                  {(["short_term", "medium_term", "long_term"] as const).map((key) => {
                    const row = matrix[key];
                    if (!row) return null;
                    const label = key === "short_term" ? "Short" : key === "medium_term" ? "Medium" : "Long";
                    return (
                      <tr key={key} className="border-t border-slate-700/50">
                        <td className="px-3 py-2 text-slate-300 font-medium">
                          {label}
                          <span className="block text-[10px] text-slate-500 font-normal">{row.stance}</span>
                        </td>
                        <td className="px-3 py-2">
                          <ActionChip action={row.action} />
                        </td>
                        <td className="px-3 py-2 text-slate-400 text-xs hidden sm:table-cell">
                          {(row.bullets ?? [])[0]}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* IF/THEN */}
        {scenarios.length > 0 && (
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-2 flex items-center gap-1">
              <GitBranch className="h-3.5 w-3.5" /> Today&apos;s key scenarios
            </p>
            <ul className="space-y-2">
              {scenarios.map((s, i) => (
                <li key={i} className="rounded-lg border border-violet-500/25 bg-violet-950/15 px-3 py-2">
                  <p className="text-sm font-medium text-violet-200">IF {s.condition}</p>
                  {s.impact && <p className="text-xs text-slate-400 mt-0.5">→ {s.impact}</p>}
                  {s.action && <p className="text-xs text-emerald-300/90 mt-1">Action: {s.action}</p>}
                  {s.probability_pct != null && (
                    <span className="text-[10px] text-slate-500">~{s.probability_pct}% historical bucket</span>
                  )}
                  {s.gap_fade_note && <p className="text-[10px] text-slate-500 mt-1">{s.gap_fade_note}</p>}
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Portfolio risk */}
        {risk && (
          <div className="rounded-lg border border-slate-700/60 bg-slate-800/30 p-3">
            <p className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-2 flex items-center gap-1">
              <Shield className="h-3.5 w-3.5" /> Your portfolio risk
            </p>
            <p className="text-sm text-slate-200">
              Risk score:{" "}
              <span className={clsx("font-mono font-bold", (risk.score ?? 0) >= 7 ? "text-amber-400" : "text-emerald-400")}>
                {risk.score}
              </span>
              <span className="text-slate-500 text-xs ml-1">{risk.score_scale}</span>
            </p>
            {(risk.adjustments ?? []).length > 0 && (
              <ul className="mt-2 space-y-1 text-xs text-amber-200/90 list-disc list-inside">
                {risk.adjustments!.map((a, i) => (
                  <li key={i}>{a}</li>
                ))}
              </ul>
            )}
            {(risk.do_nothing_if ?? []).length > 0 && (
              <p className="text-[10px] text-slate-500 mt-2 flex items-start gap-1">
                <TrendingUp className="h-3 w-3 shrink-0 mt-0.5" />
                Do nothing if: {risk.do_nothing_if!.join("; ")}
              </p>
            )}
          </div>
        )}

        {hasContextPillars && (
          <div className="border-t border-slate-700/50 pt-4">
            <button
              type="button"
              onClick={() => setContextOpen((o) => !o)}
              className="text-xs font-semibold uppercase tracking-wider text-slate-400 hover:text-slate-200 flex items-center gap-1"
            >
              <RotateCw className="h-3.5 w-3.5" />
              {contextOpen ? "Hide" : "Show"} context pillars (sentiment · earnings · triggers)
            </button>
            {contextOpen && (
              <div className="mt-3 space-y-3">
                {breadth?.plain_english && (
                  <div className="rounded-lg border border-slate-700/50 bg-slate-800/25 px-3 py-2 text-xs text-slate-400">
                    <span className="text-slate-300 font-medium">Breadth: </span>
                    {breadth.plain_english}
                    {breadth.data_note && <span className="block text-[10px] text-slate-600 mt-1">{breadth.data_note}</span>}
                  </div>
                )}
                {crowd?.plain_english && (
                  <div className="rounded-lg border border-slate-700/50 bg-slate-800/25 px-3 py-2">
                    <p className="text-xs font-medium text-slate-400 flex items-center gap-1">
                      <Users className="h-3.5 w-3.5" /> Crowd positioning
                    </p>
                    {crowd.fear_greed?.score != null && (
                      <p className="text-sm text-slate-200 mt-1">
                        Fear & Greed {crowd.fear_greed.score} ({crowd.fear_greed.rating})
                      </p>
                    )}
                    <p className="text-xs text-slate-400 mt-0.5">{crowd.plain_english}</p>
                    {crowd.aaii?.note && <p className="text-[10px] text-slate-500 mt-1">{crowd.aaii.note}</p>}
                  </div>
                )}
                {earningsPulse?.plain_english && (
                  <div className="rounded-lg border border-slate-700/50 bg-slate-800/25 px-3 py-2">
                    <p className="text-xs font-medium text-slate-400 flex items-center gap-1">
                      <Calendar className="h-3.5 w-3.5" /> Earnings season
                    </p>
                    <p className="text-sm text-slate-200 mt-1">
                      {earningsPulse.phase}
                      {earningsPulse.beat_rate?.beat_pct != null && (
                        <span className="text-slate-500"> · ~{earningsPulse.beat_rate.beat_pct}% beat (sample)</span>
                      )}
                    </p>
                    <p className="text-xs text-slate-400 mt-0.5">{earningsPulse.plain_english}</p>
                  </div>
                )}
                {(triggers?.headline || triggers?.tech_rule) && (
                  <div className="rounded-lg border border-sky-500/20 bg-sky-950/15 px-3 py-2">
                    <p className="text-xs font-medium text-sky-300/90 flex items-center gap-1">
                      <Target className="h-3.5 w-3.5" /> Trigger levels
                    </p>
                    {triggers.headline && <p className="text-xs text-slate-300 mt-1">{triggers.headline}</p>}
                    {triggers.tech_rule && <p className="text-[11px] text-slate-500 mt-1">{triggers.tech_rule}</p>}
                  </div>
                )}
                {rotation?.plain_english && (
                  <div className="rounded-lg border border-slate-700/50 bg-slate-800/25 px-3 py-2 text-xs text-slate-400">
                    <span className="text-slate-300 font-medium">Sector rotation: </span>
                    {rotation.plain_english}
                  </div>
                )}
                {personalEarnings?.items && personalEarnings.items.length > 0 && (
                  <div className="rounded-lg border border-amber-500/20 bg-amber-950/10 px-3 py-2">
                    <p className="text-xs font-medium text-amber-300/90">Your earnings calendar</p>
                    <ul className="mt-1 space-y-0.5 text-[11px] text-amber-200/80">
                      {personalEarnings.items.slice(0, 5).map((it) => (
                        <li key={it.ticker}>
                          {it.ticker} ({it.days_until}d): {it.action}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {data.disclaimer && <p className="text-[10px] text-slate-600">{data.disclaimer}</p>}
      </div>
    </div>
  );
}
