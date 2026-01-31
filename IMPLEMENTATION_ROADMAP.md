# Implementation Roadmap: Stock Investing Model

## Tech Stack (Recommended)

| Layer | Choice | Why |
|-------|--------|-----|
| **Data (v1)** | yfinance | Free, no API key; good for prototype. |
| **Data (v2)** | FMP or Tiingo | Reliable EOD + fundamentals; ~$19–29/mo. |
| **Compute** | Python 3.10+ | Pandas, NumPy for signals. |
| **Storage (v1)** | JSON / SQLite | Last run state, portfolio, watchlist. |
| **Scheduler** | Windows Task Scheduler / cron / GitHub Actions | Daily run after market close. |
| **Alerts** | Email (smtplib) or Telegram/Discord webhook | One digest or per-alert. |
| **UI (later)** | Streamlit or FastAPI + simple frontend | Optional; CLI/CSV is enough for v1. |

---

## Folder Structure (Suggested)

```
stock-investing-model/
├── config/
│   └── config.yaml          # watchlist, portfolio, alert thresholds
├── data/
│   └── last_run.json        # previous scores/regimes for diff
├── signals/
│   ├── __init__.py
│   ├── fetcher.py           # fetch OHLCV (yfinance / API)
│   ├── indicators.py        # MA, RSI, MACD, composite
│   └── regime.py            # regime + "changed?" logic
├── portfolio/
│   ├── __init__.py
│   └── doctor.py            # holdings + suggestions
├── alerts/
│   ├── __init__.py
│   └── notifier.py          # email / Telegram
├── scripts/
│   ├── run_daily.py         # main: fetch → signals → persist → alerts
│   └── backtest_simple.py   # score vs forward returns
├── ANALYSIS_AND_RECOMMENDATIONS.md
├── IMPLEMENTATION_ROADMAP.md
├── requirements.txt
└── README.md
```

---

## Phase 1 Checklist (Core)

- [ ] `requirements.txt`: yfinance, pandas, numpy
- [ ] `signals/fetcher.py`: download OHLCV with NaN/short-history handling
- [ ] `signals/indicators.py`: MA20/50/200, RSI(14), MACD(12,26,9), composite 0–100
- [ ] `signals/regime.py`: UP/NEUTRAL/DOWN from composite; optional “previous regime” for alerts
- [ ] Config: watchlist as list of tickers
- [ ] `run_daily.py`: loop watchlist → get_signals → print table (CSV/console)
- [ ] Test on SPY, QQQ, GLD, SLV, AAPL, MSFT

---

## Phase 2 Checklist (Alerts) ✅

- [x] `data/last_run.json`: save ticker → {score, regime, run_date}
- [x] Load previous run; compute regime_change, score_delta
- [x] `alerts/notifier.py`: send digest (e.g. “GLD: UP → NEUTRAL, score 78 → 52”)
- [ ] Schedule: run daily 1–2 hours after market close
- [x] Only send (no empty digests) when at least one alert fires (avoid empty emails)

---

## Phase 3 Checklist (Portfolio)

- [ ] Config: holdings as list of {ticker, quantity, optional cost_basis}
- [ ] `portfolio/doctor.py`: for each holding get score/regime; suggest HOLD/ADD/TRIM
- [ ] Portfolio summary: avg score, regime counts, largest position %
- [ ] Include in daily report or separate “portfolio_health” section

---

## Phase 4 Checklist (Better Data & Backtest)

- [x] Integrate FMP for EOD (optional api_key in config)
- [ ] Earnings calendar: next date per ticker; reduce score or flag “earnings in N days”
- [ ] `backtest_simple.py`: historical scores → forward 1/3/6 month returns by score bucket
- [x] Tune BUY/HOLD/SELL bands from backtest (suggested in output)

---

## Phase 5 Checklist (UX / Behavior)

- [x] Thesis storage: data/theses.yaml; “why” and “exit condition”
- [ ] “What changed?”: diff vs last run (e.g. “MA50 crossed below MA20, RSI 72”)
- [ ] Nudges: “Regime DOWN; you said you’d trim” / “Trend still strong”
- [x] Tooltips: config/tooltips.yaml; set show_tooltips: true

---

## Alert Thresholds (Starting Values)

| Rule | Default | Tune with |
|------|---------|-----------|
| Regime change | Any UP↔NEUTRAL↔DOWN | Backtest + your style |
| Score move | ≥ 15 points | Reduce if too noisy |
| Overbought | RSI > 70 | Optional “take profits” nudge |
| Oversold | RSI < 30 | Optional “swing buy” nudge |
| Concentration | Single position > 20% | Your risk tolerance |

---

## Guardrails (Reminders)

1. **Decision support only** – No auto-trading; you confirm every trade.
2. **Backtest before trust** – Validate that higher score ≈ better forward returns over 10+ years.
3. **EOD only for v1** – No intraday; focus on swing/position horizon.
4. **Log and version** – Keep config and code in git; log run times and errors for debugging.
