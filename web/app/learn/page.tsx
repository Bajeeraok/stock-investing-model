import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = { title: "Learn", alternates: { canonical: "/learn" } };

const POSTS = [
  { href: "/learn/index-funds-vs-stock-picking", title: "Index funds vs stock picking", blurb: "Why most stock pickers trail the index, and where picking can still fit." },
  { href: "/learn/spy-as-a-core-holding", title: "Using SPY as a core holding", blurb: "A core-and-satellite approach: a broad index core, with any individual stocks around the edges." },
  { href: "/learn/protecting-against-big-drops", title: "Protecting against big drops", blurb: "Sizing, rebalancing, stops and cash buffers, and what each one costs you." },
  { href: "/learn/report-card", title: "Weekly model report card", blurb: "What the Thrive Alpha model said versus what happened, compared with buy-and-hold and SPY." },
  { href: "/learn/market-recap", title: "Daily market recap", blurb: "The pre-open read, how the day actually closed, and how often our ranges held." },
];

export default function LearnIndex() {
  return (
    <>
      <h1>Learn to invest with evidence, not hype</h1>
      <p className="text-slate-400">
        Plain-English guides and an honest scorecard of our own model, including when it does no better than simply
        holding the index.
      </p>
      <ul className="!list-none !pl-0 space-y-3">
        {POSTS.map((p) => (
          <li key={p.href} className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
            <Link href={p.href} className="font-semibold text-emerald-400 hover:underline">{p.title}</Link>
            <p className="!my-1 text-sm text-slate-400">{p.blurb}</p>
          </li>
        ))}
      </ul>
    </>
  );
}
