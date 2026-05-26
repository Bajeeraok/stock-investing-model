"use client";

import { clsx } from "clsx";
import { useState } from "react";
import { Thermometer, Grid3X3, GitBranch, HelpCircle, Shield, TrendingUp, Users, Calendar, Target, RotateCw } from "lucide-react";

export interface MarketContextBlock {
  quadrant?: string;
  primary_message?: string;
  explanation?: string;
  historical_analog?: string;
  coexistence_note?: string;
  temperature_label?: string;
  regime_label?: string;
  hmm_bull_pct?: number;
  bull_case_trigger?: string;
  bear_case_trigger?: string;
}

export interface RetailMarketDecisions {
  market_context?: MarketContextBlock;
  morning_checklist?: { time: string; task: string }[];
  overnight_delta?: { summary?: string; lines?: { text: string }[] };
  hold_vs_trade?: { headline?: string; answer?: string; bullets?: string[] };
  five_questions?: { question: string; answer: string }[];
  market_temperature?: {
    level?: string;
    label?: string;
    vix?: number | null;
    drivers?: string[];
    interpretation?: string;
    macro_overlay?: string | null;
    timeframe_note?: string;
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
    spy_put_call?: {
      ratio?: number;
      pc_oi_ratio?: number;
      plain_english?: string;
      source?: string;
      signal?: string;
    } | null;
    contrarian?: { plain_english?: string; signal?: string } | null;
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
  credit_pulse?: {
    signal?: string;
    hy_spread_pct?: number;
    plain_english?: string;
    yield_curve_note?: string;
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
  WAIT: "bg-violet-500/20 text-violet-300 border-violet-500/40",
};

function ActionChip({ action }: { action?: string }) {
  if (!action) return null;
  return (
    <span className={clsx("text-xs font-semibold px-2 py-0.5 rounded border uppercase", ACTION_STYLE[action] ?? ACTION_STYLE.HOLD)}>
      {action}
    </span>
  );
}

export function RetailMarketDecisionsPanel({
  data,
  macroBackdrop,
}: {
  data: RetailMarketDecisions | null | undefined;
  /** Yields, calendar, seasonality — detail only; headline lives in unified hero above. */
  macroBackdrop?: {
    bullets?: string[];
    disclaimer?: string;
  } | null;
}) {
  const [contextExpanded, setContextExpanded] = useState(false);
  const [macroExpanded, setMacroExpanded] = useState(false);

  if (!data) return null;

  const macroBullets = (macroBackdrop?.bullets ?? []).filter(
    (b) => !b.startsWith("Unified read:") && !b.startsWith("Long-term SPY regime:"),
  );

  const ctx = data.market_context;
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
  const credit = data.credit_pulse;
  const personalEarnings = data.personal_earnings_calendar;
  const checklist = data.morning_checklist ?? [];
  const overnight = data.overnight_delta;
  const hasContextPillars = Boolean(crowd || earningsPulse || triggers || rotation || breadth || credit || personalEarnings);

  return (
    <div className="rounded-xl border border-emerald-500/20 bg-slate-900/60 overflow-hidden space-y-0">
      <div className="px-4 py-3 border-b border-slate-700/60 bg-slate-800/40">
        <h2 className="text-base font-semibold text-slate-100 flex items-center gap-2">
          <HelpCircle className="h-5 w-5 text-emerald-400" />
          What should I do today?
        </h2>
        <p className="text-xs text-slate-500 mt-1">One unified read — short-term fear vs long-term regime reconciled below.</p>
      </div>

      <div className="p-4 space-y-5">
        {/* Unified market context — hero */}
        {ctx?.primary_message && (
          <div className="rounded-lg border border-emerald-500/30 bg-emerald-950/20 p-4 space-y-2">
            <p className="text-sm font-semibold text-emerald-200">{ctx.primary_message}</p>
            {ctx.explanation && <p className="text-sm text-slate-300 leading-snug">{ctx.explanation}</p>}
            <div className="flex flex-wrap gap-2 text-[11px]">
              {ctx.temperature_label && (
                <span className="px-2 py-0.5 rounded border border-sky-500/30 text-sky-300">
                  Short-term: {ctx.temperature_label}
                </span>
              )}
              {ctx.regime_label && (
                <span className="px-2 py-0.5 rounded border border-emerald-500/30 text-emerald-300">
                  Regime: {ctx.regime_label}
                  {ctx.hmm_bull_pct != null && ` (~${ctx.hmm_bull_pct}% bull)`}
                </span>
              )}
            </div>
            {ctx.coexistence_note && <p className="text-xs text-slate-400">{ctx.coexistence_note}</p>}
            {ctx.historical_analog && (
              <p className="text-[11px] text-slate-500">Historical analog: {ctx.historical_analog}</p>
            )}
            {(ctx.bull_case_trigger || ctx.bear_case_trigger) && (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 pt-1 text-[11px]">
                {ctx.bull_case_trigger && (
                  <p className="text-emerald-300/80">Bull case: {ctx.bull_case_trigger}</p>
                )}
                {ctx.bear_case_trigger && (
                  <p className="text-amber-300/80">Bear case: {ctx.bear_case_trigger}</p>
                )}
              </div>
            )}
          </div>
        )}

        {overnight?.summary && (
          <div className="rounded-lg border border-slate-700/60 bg-slate-800/30 px-3 py-2">
            <p className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-1">What changed overnight</p>
            <p className="text-sm text-slate-200">{overnight.summary}</p>
            {(overnight.lines ?? []).length > 0 && (
              <ul className="mt-1 space-y-0.5 text-xs text-slate-500">
                {overnight.lines!.map((l) => (
                  <li key={l.text}>{l.text}</li>
                ))}
              </ul>
            )}
          </div>
        )}

        {checklist.length > 0 && (
          <div className="rounded-lg border border-slate-700/60 bg-slate-800/30 px-3 py-2">
            <p className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-2">Today&apos;s checklist</p>
            <ul className="space-y-1.5">
              {checklist.map((c, i) => (
                <li key={i} className="text-sm text-slate-300 flex gap-2">
                  <span className="text-slate-500 shrink-0 text-xs font-mono min-w-[5.5rem]">{c.time}</span>
                  <span>{c.task}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Five questions */}
        {questions.length > 0 && (
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-2">Your five questions</p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
              {questions.map((q) => (
                <div key={q.question} className="rounded-lg border border-slate-700/60 bg-slate-800/30 px-3 py-2">
                  <p className="text-xs font-medium text-slate-400">{q.question}</p>
                  <p className="text-sm text-slate-200 mt-0.5 leading-snug whitespace-pre-line">{q.answer}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {data.hold_vs_trade?.answer && (
          <div className="rounded-lg border border-sky-500/30 bg-sky-950/25 px-4 py-3">
            <p className="text-xs font-semibold uppercase tracking-wider text-sky-300/90 mb-1">
              {data.hold_vs_trade.headline ?? "Long-term hold vs tactical trim?"}
            </p>
            <p className="text-sm text-slate-300 leading-snug">{data.hold_vs_trade.answer}</p>
            {(data.hold_vs_trade.bullets ?? []).length > 0 && (
              <ul className="mt-2 space-y-1.5 text-sm text-slate-300">
                {data.hold_vs_trade.bullets!.map((b) => (
                  <li key={b} className="flex gap-2">
                    <span className="text-sky-400 shrink-0">→</span>
                    <span>{b}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        {/* Temperature */}
        {temp && (
          <div className={clsx("rounded-lg border p-4", TEMP_STYLE[temp.level ?? "warm"] ?? TEMP_STYLE.warm)}>
            <div className="flex items-center gap-2 mb-2">
              <Thermometer className="h-4 w-4 shrink-0" />
              <span className="text-sm font-semibold uppercase tracking-wide">
                Sentiment temperature: {temp.label}
                <span className="text-[10px] font-normal normal-case text-slate-400 ml-2">(days–weeks)</span>
              </span>
            </div>
            {temp.drivers && temp.drivers.length > 0 && (
              <p className="text-xs opacity-80 mb-2">{temp.drivers.join(" · ")}</p>
            )}
            <p className="text-sm leading-relaxed">{temp.interpretation}</p>
            {temp.macro_overlay && <p className="text-xs text-amber-200/80 mt-2">{temp.macro_overlay}</p>}
            {temp.timeframe_note && <p className="text-[10px] text-slate-500 mt-1">{temp.timeframe_note}</p>}
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
          <div className="border-t border-slate-700/50 pt-4 space-y-3">
            <p className="text-xs font-semibold uppercase tracking-wider text-slate-500 flex items-center gap-1">
              <RotateCw className="h-3.5 w-3.5" /> Context pillars
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
              {breadth?.plain_english && (
                <div className="rounded-lg border border-emerald-500/20 bg-emerald-950/10 px-3 py-2 text-slate-300">
                  <span className="text-emerald-400/90 font-medium">Breadth: </span>
                  {breadth.plain_english}
                </div>
              )}
              {credit?.plain_english && (
                <div className="rounded-lg border border-slate-700/50 bg-slate-800/25 px-3 py-2 text-slate-300">
                  <span className="text-slate-200 font-medium">Credit: </span>
                  {credit.hy_spread_pct != null && (
                    <span className="text-slate-400">HY spread {credit.hy_spread_pct}% — </span>
                  )}
                  {credit.plain_english}
                </div>
              )}
              {triggers?.headline && (
                <div className="rounded-lg border border-sky-500/20 bg-sky-950/15 px-3 py-2 text-slate-300">
                  <Target className="h-3.5 w-3.5 inline mr-1 text-sky-400" />
                  {triggers.headline}
                </div>
              )}
              {rotation?.plain_english && (
                <div className="rounded-lg border border-slate-700/50 bg-slate-800/25 px-3 py-2 text-slate-400">
                  {rotation.plain_english}
                </div>
              )}
              {crowd?.fear_greed?.score != null && (
                <div className="rounded-lg border border-slate-700/50 bg-slate-800/25 px-3 py-2 text-slate-300">
                  <span className="text-violet-300/90 font-medium">Sentiment: </span>
                  Fear & Greed {crowd.fear_greed.score}
                  {crowd.fear_greed.rating ? ` (${crowd.fear_greed.rating})` : ""}
                  {crowd.contrarian?.plain_english && (
                    <span className="text-slate-400"> — {crowd.contrarian.plain_english}</span>
                  )}
                </div>
              )}
              {crowd?.spy_put_call?.ratio != null && (
                <div className="rounded-lg border border-violet-500/20 bg-violet-950/10 px-3 py-2 text-slate-300">
                  <span className="text-violet-300/90 font-medium">Positioning: </span>
                  {crowd.spy_put_call.plain_english ?? `Put/Call ${crowd.spy_put_call.ratio}`}
                </div>
              )}
              {earningsPulse?.phase && (
                <div className="rounded-lg border border-slate-700/50 bg-slate-800/25 px-3 py-2 text-slate-400">
                  Earnings {earningsPulse.phase}: {earningsPulse.plain_english}
                </div>
              )}
            </div>
            <button
              type="button"
              onClick={() => setContextExpanded((o) => !o)}
              className="text-xs text-slate-500 hover:text-slate-300"
            >
              {contextExpanded ? "Hide" : "Show"} full pillar detail
            </button>
            {contextExpanded && (
              <div className="mt-2 space-y-3">
                {breadth?.plain_english && (
                  <div className="rounded-lg border border-slate-700/50 bg-slate-800/25 px-3 py-2 text-xs text-slate-400">
                    <span className="text-slate-300 font-medium">Breadth: </span>
                    {breadth.plain_english}
                    {breadth.data_note && <span className="block text-[10px] text-slate-600 mt-1">{breadth.data_note}</span>}
                  </div>
                )}
                {crowd && (crowd.fear_greed?.score != null || crowd.spy_put_call?.ratio != null) && (
                  <div className="rounded-lg border border-slate-700/50 bg-slate-800/25 px-3 py-2">
                    <p className="text-xs font-medium text-slate-400 flex items-center gap-1">
                      <Users className="h-3.5 w-3.5" /> Crowd positioning
                    </p>
                    {crowd.fear_greed?.score != null && (
                      <p className="text-sm text-slate-200 mt-1">
                        Fear & Greed {crowd.fear_greed.score} ({crowd.fear_greed.rating})
                      </p>
                    )}
                    {crowd.spy_put_call?.ratio != null && (
                      <p className="text-sm text-slate-200 mt-1">
                        SPY P/C {crowd.spy_put_call.ratio}
                        {crowd.spy_put_call.pc_oi_ratio != null && (
                          <span className="text-slate-500"> · OI P/C {crowd.spy_put_call.pc_oi_ratio}</span>
                        )}
                      </p>
                    )}
                    {crowd.spy_put_call?.plain_english && (
                      <p className="text-xs text-slate-400 mt-0.5">{crowd.spy_put_call.plain_english}</p>
                    )}
                    {crowd.contrarian?.plain_english && (
                      <p className="text-xs text-slate-400 mt-0.5">{crowd.contrarian.plain_english}</p>
                    )}
                    {crowd.aaii?.note && <p className="text-[10px] text-slate-500 mt-1">{crowd.aaii.note}</p>}
                    {crowd.spy_put_call?.source && (
                      <p className="text-[10px] text-slate-600 mt-1">{crowd.spy_put_call.source}</p>
                    )}
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

        {macroBullets.length > 0 && (
          <div className="border-t border-slate-700/50 pt-3">
            <button
              type="button"
              onClick={() => setMacroExpanded((o) => !o)}
              className="text-xs font-semibold uppercase tracking-wider text-slate-500 hover:text-slate-300 flex items-center gap-1"
            >
              Macro backdrop detail
              <span className="text-[10px] font-normal normal-case text-slate-600">
                ({macroBullets.length} items — yields, calendar, seasonality)
              </span>
            </button>
            {macroExpanded && (
              <ul className="mt-2 list-disc list-inside text-xs text-slate-400 space-y-1 max-w-3xl">
                {macroBullets.map((b) => (
                  <li key={b}>{b}</li>
                ))}
              </ul>
            )}
            {macroExpanded && macroBackdrop?.disclaimer && (
              <p className="text-[10px] text-slate-600 leading-snug mt-2">{macroBackdrop.disclaimer}</p>
            )}
          </div>
        )}

        {data.disclaimer && <p className="text-[10px] text-slate-600">{data.disclaimer}</p>}
      </div>
    </div>
  );
}
