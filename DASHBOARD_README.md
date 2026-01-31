# Stock Investing Model - Dashboard Setup

A cutting-edge dashboard built with **FastAPI** (backend) and **Next.js + React** (frontend) that displays all model features.

## Quick Start

### 1. Install dependencies

```bash
# Backend (from project root)
pip install -r requirements.txt

# Frontend
cd web
npm install
```

### 2. Run the app

**Terminal 1 - FastAPI backend:**
```bash
cd stock-investing-model
python -m uvicorn api.main:app --reload --host 127.0.0.1 --port 8002
```

**Terminal 2 - Next.js frontend:**
```bash
cd stock-investing-model/web
npm run dev
```

**Open:** [http://localhost:3001](http://localhost:3001)

> **Note:** The first dashboard load runs the full analysis (signals, portfolio, opportunities) and may take **1-2 minutes**. Subsequent refreshes also trigger a full run.

## Features

| Section | Description |
|---------|-------------|
| **Story Change Alerts** | Regime flips and score drops - review first |
| **Portfolio Summary** | Total value, avg score, regime mix, largest position |
| **Score Chart** | Bar chart of composite scores by ticker (green=BUY, red=SELL, gray=HOLD) |
| **Regime Chart** | Pie chart of UP/NEUTRAL/DOWN distribution |
| **Daily Signals** | Full table: ticker, close, score, RSI, regime, signal, multi-horizon suggestions |
| **Portfolio Holdings** | Per-holding value, %, score, regime, suggestion |
| **Consider Trim** | Holdings with score < 40 (protect gains) |
| **Opportunities** | Long-term growth candidates (not in portfolio) |
| **Thesis Check** | Thesis + exit condition; nudges when conditions match |
| **What Changed** | Diff vs last run (MA50 cross, RSI, score, regime) |

## API Endpoints

- `GET /api/health` - Health check
- `GET /api/dashboard` - Full dashboard data (runs analysis)
- `GET /api/signals` - Signals only
- `GET /api/backtest` - Backtest results
- `GET /api/theses` - Thesis storage
- `GET /api/config` - Current config

## Tech Stack

- **Backend:** FastAPI, Uvicorn
- **Frontend:** Next.js 14, React 18, TypeScript, Tailwind CSS, Recharts, Lucide React
- **Style:** Dark theme, emerald accent, responsive layout
