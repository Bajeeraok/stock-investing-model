# Stock Investing Model - Dashboard

Next.js + React dashboard for the Stock Investing Model.

## Setup

```bash
cd web
npm install
```

## Run

1. **Start the FastAPI backend** (from project root):

   ```bash
   cd ../backend
   python -m uvicorn api.main:app --reload --host 127.0.0.1 --port 8002
   ```

2. **Start the Next.js frontend**:

   ```bash
   npm run dev
   ```

3. Open [http://localhost:3001](http://localhost:3001)

## Features

- **Story Change Alerts** - Regime flips and score drops
- **Portfolio Summary** - Total value, avg score, regime mix, largest position
- **Score Chart** - Bar chart of composite scores by ticker
- **Regime Chart** - Pie chart of UP/NEUTRAL/DOWN distribution
- **Daily Signals** - Full signals table with score, RSI, regime, suggestions
- **Portfolio Holdings** - Per-holding value, %, score, regime, suggestion
- **Consider Trim** - Holdings with score < 40
- **Opportunities** - Long-term growth candidates
- **Thesis Check** - Thesis + exit condition with nudges
- **What Changed** - Diff vs last run

## Environment

- `NEXT_PUBLIC_API_URL` - FastAPI base URL (empty = proxy to localhost:8002)
- **Backend:** `DATA_ROOT` - Persistent data directory for EOD snapshots, last_run, paper trades. Set to a mounted volume path so data survives restarts. Alternatively, EOD snapshots are also stored in **Redis** when `REDIS_URL` is set, so they persist across restarts without a volume.
