# Best setups / full-go forward test on production snapshots (2026-11-16)

**Question:** do the model's entries (full go, the Best setups list) beat SPY? The live list record showed −4.6% (Swing) / −7.7% (Owner) on 17 picks from Nov 6–13.

**Data:** 121 production EOD snapshots (2026-05-27 → 2026-11-13, `GET /api/eod/snapshots/{date}`), i.e. what the model said that night under the rules live at the time. yfinance adjusted daily prices, 0.2% round-trip cost, return vs SPY over the same sessions. A ticker counts once per run of consecutive days in a group (first day). Script: `scripts/best_setups/bt.py`.

## Live list record (Nov 6–13)

| Mode | Picks | Avg | vs SPY same days |
|---|---|---|---|
| Swing | 9 | −4.6% | −2.6 pts |
| Owner | 8 | −7.7% | −6.1 pts |

Most losers (BE, NBIS, STX, SOUN, IONQ, RKLB, NVDA) were 20–70% off their highs and below the 200-day. They were listed through the regime catch-up shortcut (full go with Trend weather failing), removed on Nov 14 (658c728). The uptrend picks beat SPY: COP +4.3, MSFT +2.1, BAC +0.1 pts.

## 20-session forward results by entry mode

| Group | Entries | Avg | vs SPY | Beat SPY | NW t |
|---|---|---|---|---|---|
| All rows (baseline) | 9,931 | −0.6% | −0.9 | 46% | −0.7 |
| Full go | 48 | −0.8% | +0.5 | 58% | 0.3 |
| Swing-list proxy (full go, price in band +3%, stop below) | 45 | −0.1% | +1.1 | 60% | 1.5 |
| Starter only | 331 | −4.0% | −3.7 | 37% | −3.0 |
| Hard lock | 444 | −1.5% | −2.5 | 43% | −4.0 |

Swing-list first touch (t1 vs stop, 63 sessions): 32 target (+3.6%), 42 stop (−2.0%), 4 open; about +0.4% per trade.

## Verdict

- **Gates help avoid losers:** locked names lagged SPY by 2.5 pts (t −4.0); starter entries lagged by 3.7 pts (t −3.0), which confirms turning starters off.
- **Full go / list picks are not proven:** +0.5 to +1.1 pts vs SPY on 45–48 entries, t well below 3. Full go only appears from 2026-08-26 (after HOLD-by-default), so no 60-session windows yet.
- **Not testable from snapshots:** Owner mode and the list's edge ranking need detail-level plans (12-month target/stop, level odds), which snapshots don't store.
- **Live record now split:** headline = picks since the Nov 14 fix; earlier picks are shown separately, all vs SPY.

**Revisit:** when full go has 30+ entries with complete 60-session windows, or after 30+ list picks under the current rules. Consider saving the Best setups rows (target/stop/edge) in the EOD snapshot so the ranking can be tested.
