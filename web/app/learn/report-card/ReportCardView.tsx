"use client";

import { useEffect, useState } from "react";
import { apiUrl } from "@/lib/apiBase";
import { ReportCardPanel, type ReportCard } from "@/components/dashboard/ReportCardPanel";

export default function ReportCardView() {
  const [rc, setRc] = useState<ReportCard | null>(null);
  const [state, setState] = useState<"loading" | "ok" | "error">("loading");
  useEffect(() => {
    fetch(apiUrl("/api/dashboard/analysis/forward-tracking"))
      .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
      .then((d) => {
        setRc((d?.forward_tracking ?? d)?.report_card ?? null);
        setState("ok");
      })
      .catch(() => setState("error"));
  }, []);

  if (state === "loading") return <p className="text-slate-500">Loading report card…</p>;
  if (state === "error" || !rc) return <p className="text-slate-500">The report card is temporarily unavailable.</p>;
  if (rc.public && rc.ready_to_publish) return <ReportCardPanel data={rc} />;

  return (
    <section className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
      <h2 className="!mt-0">Not published yet</h2>
      <p>
        Model {rc.model_version} has {rc.trading_days_scored} scored trading day{rc.trading_days_scored === 1 ? "" : "s"} so far.
        We only publish results once the bar below is met, so a lucky or unlucky few weeks don&apos;t pass for evidence.
      </p>
      <ul className="!list-none !pl-0">
        {rc.publish_checks.map((c) => (
          <li key={c.label} className={c.ok ? "text-emerald-400" : "text-slate-400"}>
            {c.ok ? "✓" : "○"} {c.label}: <span className="text-slate-500">{c.detail}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
