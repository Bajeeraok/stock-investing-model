import type { Metadata } from "next";
import Link from "next/link";
import { Disclaimer } from "./Disclaimer";

const PUBLISHED = process.env.NEXT_PUBLIC_PUBLISH_CONTENT === "1";
const SITE = process.env.NEXT_PUBLIC_SITE_URL || "https://thrivealpha.com";

export const metadata: Metadata = {
  metadataBase: new URL(SITE),
  title: { default: "Thrive Alpha Learn", template: "%s | Thrive Alpha" },
  description: "Plain-English investing education, a weekly model report card and a daily market recap. Education only, not advice.",
  // Unlisted until the domain goes live and publishing is switched on.
  robots: PUBLISHED ? { index: true, follow: true } : { index: false, follow: false },
};

const NAV = [
  { href: "/learn", label: "Learn" },
  { href: "/learn/report-card", label: "Weekly report card" },
  { href: "/learn/market-recap", label: "Daily market recap" },
];

export default function LearnLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-slate-950 text-slate-200">
      <header className="border-b border-slate-800">
        <nav className="mx-auto flex max-w-3xl flex-wrap items-center gap-4 px-4 py-4 text-sm">
          <Link href="/learn" className="font-bold text-emerald-400">Thrive Alpha</Link>
          {NAV.map((n) => (
            <Link key={n.href} href={n.href} className="text-slate-400 hover:text-slate-100">{n.label}</Link>
          ))}
          {!PUBLISHED && <span className="ml-auto rounded bg-slate-800 px-2 py-0.5 text-xs text-slate-400">Unlisted preview</span>}
        </nav>
      </header>
      <main className="mx-auto max-w-3xl px-4 py-10 [&_h1]:text-3xl [&_h1]:font-extrabold [&_h2]:mt-10 [&_h2]:mb-3 [&_h2]:text-xl [&_h2]:font-bold [&_p]:my-3 [&_p]:leading-relaxed [&_ul]:my-3 [&_ul]:list-disc [&_ul]:pl-6 [&_li]:my-1 [&_table]:my-4 [&_table]:w-full [&_table]:text-sm [&_th]:border-b [&_th]:border-slate-700 [&_th]:p-2 [&_th]:text-left [&_td]:border-b [&_td]:border-slate-800 [&_td]:p-2">
        {children}
        <Disclaimer />
      </main>
    </div>
  );
}
