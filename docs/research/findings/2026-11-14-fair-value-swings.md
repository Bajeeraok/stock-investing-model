# Fair value swings (INTC, NOW, APP, HUM, ORCL…)
2026-11-14 · Status: fixed

**Problem.** Fair values were stable Nov 9–12, then the Nov 13 8 PM run produced very different values and
flipped valuation gates (NVDA $233.70 → $169.53 → $233.69 with no earnings in between).

| Stock | Nov 9–12 | Nov 13 run | After fix |
|---|---|---|---|
| INTC | $107.50 | $46.81 | $107.50 |
| NOW | $141.78 | $87.80 | $141.78 |
| APP | $495 | $368 | $509 |
| HUM | ~$260 | $502 | $264 |
| KO | ~$87 | $108 | $87 |

**Likely cause (unconfirmed).** Data feeds failing on a day with many deploys and audit reruns; the
earnings-data plan refuses profile / key-metrics calls, so most inputs come from Yahoo.

**Why checks missed it.** The audit looked at one day at a time; the 15% hold check's memory was wiped on
every deploy, weekend reruns counted as "confirmed on a later day", and analyst-based values skipped it.

**Fix.** Stability state in Redis; seed from the median of the last 5 nightly runs; a jump is confirmed only
in a later trading session; every fair value is checked; last accepted value reused up to 10 days.
Audit gained day-over-day FV jump and list-vs-page checks, a rerun-on-restart, and an error alert.
Audit errors went 57 → 0 after the Nov 13 snapshot was rerun.

**Code.** `backend/signals/fv_stability.py`; rule in `docs/signals/SIGNAL_RULES.md`.
