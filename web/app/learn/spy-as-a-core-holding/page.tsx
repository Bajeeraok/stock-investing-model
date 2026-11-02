import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Using SPY as a core holding",
  description: "How a core-and-satellite portfolio works: a broad S&P 500 fund as the core, with any individual stocks sized as satellites.",
  alternates: { canonical: "/learn/spy-as-a-core-holding" },
};

export default function Page() {
  return (
    <>
      <h1>Using SPY as a core holding</h1>
      <p>
        SPY is an exchange-traded fund that tracks the S&amp;P 500: about 500 large US companies weighted by market
        value. Other S&amp;P 500 funds, such as IVV and VOO, track the same index at a lower expense ratio. The idea
        below works with any of them.
      </p>
      <h2>Core and satellite</h2>
      <ul>
        <li><strong>Core:</strong> most of the portfolio sits in a broad, low-cost index fund. It captures the market's return and needs little upkeep.</li>
        <li><strong>Satellites:</strong> a smaller share goes to individual stocks or themes you have conviction in. If they lag, the core limits the damage.</li>
        <li><strong>Benchmark:</strong> judge every satellite against what the core would have earned. If your picks trail SPY for years, put more in the core.</li>
      </ul>
      <h2>Things to know about the S&amp;P 500</h2>
      <ul>
        <li>It is weighted by size, so the largest companies drive much of its moves. Recently its 10 biggest holdings have made up a large share of the index.</li>
        <li>It is US large-cap only. Small-cap, international and bond funds can broaden a portfolio.</li>
        <li>It has had deep declines: roughly 50% from 2007 to 2009, and over 30% in early 2020. Owning the core means sitting through drops like these.</li>
      </ul>
      <h2>How Thrive Alpha uses SPY</h2>
      <p>
        The app scores each stock call two ways: against holding the same stock and against holding SPY. If a stock
        and its signals can't beat SPY over time, the simpler choice is usually the index.
      </p>
    </>
  );
}
