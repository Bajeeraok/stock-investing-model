import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Protecting against big drops",
  description: "Position sizing, rebalancing, stop-losses, cash buffers and hedges: how each limits drawdowns, and what each one costs.",
  alternates: { canonical: "/learn/protecting-against-big-drops" },
};

export default function Page() {
  return (
    <>
      <h1>Protecting against big drops</h1>
      <p>
        Every protection has a cost. It usually means giving up some upside or paying for insurance. The goal isn't to
        dodge every decline, which nobody can do reliably. It's to keep any one drop from forcing you to sell at the
        worst time.
      </p>
      <h2>1. Position sizing</h2>
      <p>
        Cap how much of your portfolio any single stock can be. If a stock is 25% of your money and falls 50%, your
        portfolio drops 12.5%. At 5%, the same fall costs you 2.5%. Thrive Alpha's sizing card uses this idea: it
        suggests optional trims back to a cap, based on all your accounts combined.
      </p>
      <h2>2. Rebalancing</h2>
      <p>
        Set target weights, for example a stock/bond mix, and rebalance on a schedule or when weights drift past a band.
        This trims what has run up and adds to what has fallen. It costs some momentum on the way up.
      </p>
      <h2>3. Stop-losses</h2>
      <p>
        A stop sells after a set decline. It caps the loss on one position, but in choppy markets it can sell near a low
        just before a rebound, and prices can gap past it. Use stops as a plan you set in advance, not as a prediction.
      </p>
      <h2>4. Cash and bond buffers</h2>
      <p>
        Keeping 6–12 months of expenses, or near-term goals, in cash or short-term bonds means you won't need to sell
        stocks in a crash. The cost is lower expected returns on that money.
      </p>
      <h2>5. Hedges</h2>
      <p>
        Put options and inverse funds can offset declines, but they cost money every year and are complex. Most
        long-term investors do better with sizing and buffers.
      </p>
      <h2>Thrive Alpha's protect mode</h2>
      <p>
        Protect mode is optional insurance. When risk signals rise, it suggests trimming toward about half a position.
        It is not designed to raise returns. In calm markets it usually costs some upside. Our report card tracks what
        it costs and what it saves.
      </p>
    </>
  );
}
