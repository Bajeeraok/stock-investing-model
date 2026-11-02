import type { Metadata } from "next";
import ReportCardView from "./ReportCardView";

export const metadata: Metadata = {
  title: "Weekly model report card",
  description: "What the Thrive Alpha model said versus what happened over 20 trading days, compared with holding the same stock and holding SPY, with uncertainty ranges.",
  alternates: { canonical: "/learn/report-card" },
};

export default function Page() {
  return (
    <>
      <h1>Weekly model report card</h1>
      <p className="text-slate-400">
        Every call the current model makes is tracked for 20 trading days. We compare it with simply holding the same
        stock and with holding SPY, after a 0.10% cost on calls that change exposure. Calls on the same day move
        together, so the uncertainty ranges count days, not individual calls.
      </p>
      <ReportCardView />
    </>
  );
}
