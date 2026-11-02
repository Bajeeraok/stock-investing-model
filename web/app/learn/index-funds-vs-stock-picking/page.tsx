import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Index funds vs stock picking",
  description: "What the evidence says about index funds versus picking individual stocks, and how to decide what share of your money, if any, to put into picks.",
  alternates: { canonical: "/learn/index-funds-vs-stock-picking" },
};

export default function Page() {
  return (
    <>
      <h1>Index funds vs stock picking</h1>
      <p>
        An index fund buys every stock in an index, such as the S&amp;P 500, in proportion to its size. Stock picking
        means choosing a handful of companies you expect to beat that index. Here is what the evidence says.
      </p>
      <h2>Most professional pickers trail the index</h2>
      <p>
        S&amp;P Dow Jones Indices' long-running SPIVA reports compare active US funds with their benchmarks. Over 10-
        and 15-year periods, a large majority of US large-cap funds have trailed the S&amp;P 500 after fees. These are
        full-time professionals with research teams.
      </p>
      <h2>Why it's so hard</h2>
      <ul>
        <li><strong>Costs compound.</strong> A 1% yearly fee or trading drag takes a large bite out of 20 or 30 years of returns.</li>
        <li><strong>A few stocks drive most of the gains.</strong> Studies of US stocks find a small share of companies produced most of the market's long-run wealth creation. A concentrated portfolio can easily miss them.</li>
        <li><strong>Prices already reflect public news.</strong> Doing better means knowing something the market hasn't priced in yet.</li>
        <li><strong>Behavior.</strong> Selling after drops and chasing winners costs individual investors returns, on top of fees.</li>
      </ul>
      <h2>What our own testing found</h2>
      <p>
        We back-tested the Thrive Alpha scoring model across 10 years of S&amp;P 500 stocks. Its stock-picking scores
        did not reliably beat simply holding SPY. That is why the app defaults to <em>hold</em>, treats SPY as the
        benchmark to beat, and publishes a <a href="/learn/report-card" className="text-emerald-400 underline">weekly report card</a> instead
        of marketing claims.
      </p>
      <h2>If you still want to pick stocks</h2>
      <ul>
        <li>Keep a broad index fund as the core and limit picks to a share you can afford to underperform with.</li>
        <li>Write down why you bought each stock and what would make you sell it.</li>
        <li>Compare your picks with what SPY did over the same period, including dividends, every year.</li>
        <li>Keep any single stock a modest share of your total portfolio.</li>
      </ul>
    </>
  );
}
