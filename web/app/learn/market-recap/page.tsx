import type { Metadata } from "next";
import { MarketPulseCard } from "@/components/dashboard/MarketPulseCard";

export const metadata: Metadata = {
  title: "Daily market recap",
  description: "Each trading day: the pre-open read on SPY, the intraday likely-close range, how the day finished, and how often the ranges held.",
  alternates: { canonical: "/learn/market-recap" },
};

export default function Page() {
  return (
    <>
      <h1>Daily market recap</h1>
      <p className="text-slate-400">
        Before the open we estimate SPY&apos;s likely opening move and closing range from futures and VIX, using
        similar past days. We update the range through the day and score it against the actual close. These are
        odds based on history, not forecasts. The scorecard shows how often they held.
      </p>
      <MarketPulseCard />
    </>
  );
}
