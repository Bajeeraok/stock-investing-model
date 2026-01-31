# Stock Investing Model

A **decision-support** system for retail investors: confidence score (0–100), regime (UP/NEUTRAL/DOWN), and portfolio view. Use it to answer “buy vs sell?” and get trend-change alerts—not as autopilot.

## Features

- **Composite buy score (0–100)** from trend (MA20/50/200), RSI (asymmetric), and MACD
- **Regime**: UP / NEUTRAL / DOWN from score bands
- **Signal**: BUY / HOLD / SELL from configurable thresholds
- **Multi-horizon**: short (weeks), medium (months), long (1–2 yr) suggestions
- **Story-change alerts**: regime flip or score drop ≥15; prints to console; optional email/Telegram
- **Portfolio health**: total value, regime mix, per-holding value/%, concentration alert, cash deployment
- **Opportunity scan**: daily identification of tickers with long-term growth potential (candidates to research)
- **Earnings calendar**: flag/reduce score when earnings within N days (Phase 4)
- **Backtest**: `python scripts/backtest_simple.py` - validate score vs forward returns (Phase 4)
- **Thesis storage**: per-ticker thesis + exit condition; nudges when conditions match (Phase 5)
- **What changed**: diff vs last run (MA50 cross, RSI, score, regime) (Phase 5)
- **Tooltips**: set `show_tooltips: true` for indicator explanations (Phase 5)
- **Persistence**: `data/last_run.json` for regime-change and score-delta detection

## Quick start

```bash
cd stock-investing-model
pip install -r requirements.txt
python scripts/run_daily.py
```

Edit `config/config.yaml` to set your **watchlist** and optional **portfolio** (ticker + quantity).

## Project layout

- `config/config.yaml` – watchlist, portfolio, score/regime bands, opportunity scan
- `signals/` – fetch OHLCV, indicators, composite score, regime
- `opportunity/` – scan universe for long-term growth potential
- `scripts/run_daily.py` – daily run (use Task Scheduler / cron after market close)
- `scripts/run_opportunity_scan.py` – standalone opportunity scan (faster than full run)
- `data/last_run.json` – previous run state for alerts
- `data/theses.yaml` – thesis + exit condition per ticker (Phase 5)
- `scripts/backtest_simple.py` – backtest score vs forward returns (Phase 4)
- `scripts/add_thesis.py` – add thesis for ticker (Phase 5)
- `ANALYSIS_AND_RECOMMENDATIONS.md` – analysis and recommendations
- `IMPLEMENTATION_ROADMAP.md` – phased implementation checklist

## Alerts (Phase 2)

To receive email or Telegram when story changes occur, add to `config/config.yaml`:

```yaml
alerts:
  email:
    smtp_host: smtp.gmail.com
    smtp_port: 587
    user: your-email@gmail.com
    password: your-app-password
    from_addr: your-email@gmail.com
    to_addrs: your-email@gmail.com

# Or Telegram (bot via @BotFather, chat_id from @userinfobot)
alerts:
  telegram:
    bot_token: YOUR_BOT_TOKEN
    chat_id: YOUR_CHAT_ID
```

Leave `alerts: {}` to skip sending; alerts still print to console.

## Opportunity scan (long-term growth potential)

Identifies tickers with strong technical setup (uptrend, momentum, not overbought) as **candidates to research**—not buy recommendations.

- **Included in** `run_daily.py` by default (`run_opportunity_scan: true` in config)
- **Standalone**: `python scripts/run_opportunity_scan.py` (faster when you only want discovery)
- **Config**: `opportunity_universe` (empty = built-in ~55 liquid S&P leaders), `opportunity_criteria` (min_score, max_rsi, etc.)
- **Excludes** portfolio tickers so you see new names to consider

## Dashboard (FastAPI + Next.js)

A web dashboard displays all features. See **DASHBOARD_README.md** for setup.

```bash
# Terminal 1 - API
python -m uvicorn api.main:app --reload --port 8002

# Terminal 2 - Frontend
cd web && npm run dev
```

Open [http://localhost:3001](http://localhost:3001).

## Guardrails

- **Decision support only** – no auto-trading; you confirm every trade
- **Backtest before trust** – run `python scripts/backtest_simple.py` to validate score vs forward returns
- **EOD only** – built for swing/position horizon, not intraday

## Next steps

1. Update quantities in config/config.yaml to match your holdings
2. Schedule daily run (Task Scheduler / cron) after market close
3. Configure alerts (optional) “doctor” - see Alerts section above
4. Add paid data + backtest (Phase 4) when’re ready

See **IMPLEMENTATION_ROADMAP.md** for the full checklist.
