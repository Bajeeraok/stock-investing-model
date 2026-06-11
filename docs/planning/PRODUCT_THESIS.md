# Thrive Alpha — Product thesis (one page)

## One sentence

**Thrive Alpha is a horizon-aware decision coach for retail traders and investors: for any ticker they care about—not only what they already own—it answers *wait, add, or trim* with explicit limits, in under 30 seconds.**

---

## The problem

Retail platforms excel at **more data** (charts, screens, ratings, news). They weakly address **decisions under uncertainty**:

- Short-term tape disagrees with long-term thesis (“macro risk-off” vs “still in a bull regime”).
- The same ticker needs **different rules** for a day trade, a swing, or a core holding—but tools show one generic “buy/sell.”
- Traders with **no position yet** still need a structured read before they enter.
- Holders need **book-level** risk (concentration, earnings, trim), not another RSI in isolation.
- Overconfident scores and alert noise erode trust after one bad week.

Emotional trading is rarely “missing an indicator.” It is **acting on the wrong horizon with no reconciled story.**

---

## Who we serve

| Persona | Hold period | Primary question |
|---------|-------------|------------------|
| **Scout** (tactical) | Days–weeks | Is this setup actionable *now* at the short band? |
| **Swing** | Weeks–months | Add on pullback or trim into strength before earnings? |
| **Owner** (core) | Months–years | Is the thesis intact—accumulate, pause, or reduce? |

One product, **three lenses** (global + per-ticker). Same engine; different priority, copy, and default bands—not three separate apps.

---

## What we are (and are not)

| We are | We are not |
|--------|------------|
| Decision **support** with disclaimers and track record | Auto-trading or “AI says buy” |
| **Horizon-first** (ST · MT · LT gates, bands, stops) | A single Smart Score without context |
| **Any ticker** in watchlist / scan / type-ahead | Portfolio-only wealth tool |
| **Book-aware** when the user has holdings | A broker or tax-lot system |
| Regime + macro **reconciliation** | Another charting terminal |

---

## Core promise

> **Open any ticker. Choose your horizon (Scout / Swing / Owner). Get one primary action, where price should be, what breaks the thesis, and when doing nothing is correct.**

### For tickers you **don’t** own yet

- Same **One Answer** surface: gates, bands, street vs model, catalyst/earnings context.
- Opportunities and scanner (roadmap) surface *candidates*; the modal is the research gate before size.
- No pretend portfolio weight—copy stays “if you were to enter.”

### For tickers you **do** own

- Everything above, plus: sizing hints, trim provenance, thesis nudges, concentration and earnings in **your** book.
- Today’s 3 moves and portfolio doctor prioritize **holdings**; Signals/Roadmaps still cover the full universe.

---

## How we close the gap vs incumbents

| Retail pain | Thrive Alpha approach |
|-------------|------------------------|
| Timeframe conflict | Unified read: ST sentiment vs LT regime; matrix ST·MT·LT |
| Wrong playbook for hold period | Scout / Swing / Owner lens + per-ticker mode |
| “What about XYZ?” before buying | Full signal + detail for watchlist/universe names, not only holdings |
| Portfolio recklessness | Heat, trim drivers, stress, doctor—when book is linked |
| Trust / false precision | Forward tracking, calibration, known limits, alert provenance |
| Alert fatigue | Capped digests, “consider,” cooldown + journal direction |

We do **not** try to beat TradingView on drawing tools or Finviz on raw screen count. We win on **clarity + horizon + honesty** for the decision moment.

**UX philosophy:** Best-in-class **synthesis** — steal list density (Finviz), one-action clarity (Robinhood), trust surfaces (TipRanks), digest discipline (alert apps) — then fuse with our gate/horizon engine. Chart embeds are optional context, not the home surface. See [`TRADING_PLATFORM_UX_BENCHMARK.md`](TRADING_PLATFORM_UX_BENCHMARK.md).

---

## North-star metric

**Within 30 seconds, can the user state for their top concern (held or watchlisted):**

1. **Act, wait, or trim** (primary horizon)  
2. **Where price matters** (band / stop / target)  
3. **What would prove them wrong** (thesis or gate failure)

If yes → we delivered value that day. If no → UI or model failed, not “add another indicator.”

---

## Product shape (three surfaces, one engine)

```text
                    ┌─────────────────────────┐
                    │  Signal engine (ST/MT/LT) │
                    │  Regime · Gates · Bands   │
                    └───────────┬─────────────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        ▼                       ▼                       ▼
  Market session          Your book (optional)     Any ticker
  (pre-open, tape)        (heat, trim, thesis)     (One Answer)
```

- **Session** — What is the tape doing today? (Scout-heavy)  
- **Book** — Is my portfolio safe? (Owner / Steward-heavy)  
- **Name** — What should I do on *this* symbol at *my* horizon? (All personas)

---

## Roadmap alignment (honest)

**Shipped / in flight:** Phase A persona lens; public demo + config portfolio universe; Overview digest; provenance on alerts; horizon bands and retail action.

**Needed for the thesis above:**

- **B** — Discovery at home (scanner, hunter strip) so non-held tickers are first-class.  
- **D** — Trust on first screen (hit rates, calibration by horizon).  
- **Auth** — User-linked portfolio; config becomes dev/demo default only.  
- **Continued UX** — One action path per ticker per day; less duplicate copy.

---

## Positioning line (external)

*Thrive Alpha doesn’t tell you what to buy. It helps you decide—on any symbol, for the horizon you’re actually trading—when to act, when to wait, and when your portfolio or thesis says stop.*

---

*Living backlog: [TODO.md](../../TODO.md) (Multi-persona roadmap Phases A–E). Architecture: [CLAUDE.md](../../CLAUDE.md).*
