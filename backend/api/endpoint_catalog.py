"""
Curated API catalog for dev/ad-hoc runner UI.
Keep in sync when adding routers — or extend GET /api/dev/endpoints to merge OpenAPI.
"""
from __future__ import annotations

from typing import Any

# group, method, path template, description, optional defaults
CATALOG: list[dict[str, Any]] = [
    # Health
    {"group": "Health", "method": "GET", "path": "/api/health", "description": "Liveness check"},
    {"group": "Health", "method": "GET", "path": "/api/health/memory", "description": "Process memory snapshot"},
    # Dashboard core
    {"group": "Dashboard", "method": "GET", "path": "/api/dashboard", "description": "Full dashboard payload", "query": {"refresh": "false"}},
    {"group": "Dashboard", "method": "GET", "path": "/api/dashboard/shell", "description": "Light shell (no heavy compute)"},
    {"group": "Dashboard", "method": "GET", "path": "/api/dashboard/status", "description": "Warm/cache status"},
    {"group": "Dashboard", "method": "GET", "path": "/api/dashboard/ws-config", "description": "WebSocket URL for live cache push"},
    {"group": "Dashboard", "method": "GET", "path": "/api/dashboard/ws", "description": "WebSocket live dashboard updates (upgrade)", "external": True},
    {"group": "Dashboard", "method": "GET", "path": "/api/dashboard/signals-panel", "description": "Signals table rows (lazy)"},
    {"group": "Dashboard", "method": "GET", "path": "/api/dashboard/opportunities-bundle", "description": "Opportunities + doctor adds"},
    {"group": "Dashboard", "method": "GET", "path": "/api/dashboard/analysis-bundle", "description": "Analysis tab bundle"},
    {"group": "Dashboard", "method": "GET", "path": "/api/dashboard/analysis/forward-tracking", "description": "Forward tracking slice"},
    {"group": "Dashboard", "method": "GET", "path": "/api/dashboard/analysis/model-audit", "description": "Model audit slice"},
    {"group": "Dashboard", "method": "GET", "path": "/api/dashboard/analysis/paper-trading", "description": "Paper trading slice"},
    {"group": "Dashboard", "method": "GET", "path": "/api/dashboard/eod-universe", "description": "EOD universe table (~100 tickers)"},
    {"group": "Dashboard", "method": "GET", "path": "/api/config", "description": "Effective config (sanitized)"},
    {"group": "Dashboard", "method": "GET", "path": "/api/last-run", "description": "Previous run scores/regimes"},
    {"group": "Dashboard", "method": "GET", "path": "/api/registry", "description": "Asset registry metadata"},
    {"group": "Dashboard", "method": "GET", "path": "/api/accuracy", "description": "Price target accuracy report"},
    # Signals & backtest
    {"group": "Signals", "method": "GET", "path": "/api/signals", "description": "Run signals for tickers", "query": {"tickers": "SPY,QQQ"}},
    {"group": "Signals", "method": "GET", "path": "/api/backtest", "description": "Backtest bucket results"},
    {"group": "Signals", "method": "GET", "path": "/api/reports/monthly-signal-buckets", "description": "Monthly signal bucket report"},
    {"group": "Signals", "method": "POST", "path": "/api/test-suite", "description": "Signal test suite", "body": {"tickers": ["SPY"]}, "confirm": True},
    # Ticker detail
    {"group": "Ticker", "method": "GET", "path": "/api/ticker/{ticker}", "description": "Ticker detail bundle", "path_params": {"ticker": "SPY"}},
    {"group": "Ticker", "method": "GET", "path": "/api/ticker/{ticker}/intraday", "description": "Intraday bars", "path_params": {"ticker": "SPY"}},
    {"group": "Ticker", "method": "GET", "path": "/api/confidence/{ticker}", "description": "7-layer confidence", "path_params": {"ticker": "SPY"}},
    {"group": "Ticker", "method": "GET", "path": "/api/insights/{ticker}", "description": "Institutional insights", "path_params": {"ticker": "SPY"}},
    {"group": "Ticker", "method": "GET", "path": "/api/unified-signal/{ticker}", "description": "Unified signal payload", "path_params": {"ticker": "SPY"}},
    {"group": "Ticker", "method": "GET", "path": "/api/price-targets/{ticker}", "description": "Price targets / scenarios", "path_params": {"ticker": "SPY"}},
    {"group": "Ticker", "method": "GET", "path": "/api/classify/{ticker}", "description": "Asset classification", "path_params": {"ticker": "SPY"}},
    {"group": "Ticker", "method": "GET", "path": "/api/roadmaps", "description": "Buy/sell roadmaps", "query": {"tickers": "SPY,NVDA"}},
    {"group": "Ticker", "method": "GET", "path": "/api/live-prices", "description": "Live quote batch", "query": {"tickers": "SPY,QQQ"}},
    {"group": "Ticker", "method": "GET", "path": "/api/thrive-phase2", "description": "Thrive phase-2 intraday", "query": {"ticker": "MSFT"}},
    {"group": "Ticker", "method": "GET", "path": "/api/signal-diagnostics/{ticker}", "description": "Signal diagnostics", "path_params": {"ticker": "SPY"}},
    # Market
    {"group": "Market", "method": "GET", "path": "/api/pre-market", "description": "Pre-market rotation / ES-NQ"},
    {"group": "Market", "method": "GET", "path": "/api/market-state", "description": "Market state snapshot"},
    {"group": "Market", "method": "GET", "path": "/api/after-hours/snapshot", "description": "After-hours earnings movers"},
    # EOD & audit
    {"group": "EOD & Audit", "method": "GET", "path": "/api/eod/status", "description": "EOD scheduler + snapshot status"},
    {"group": "EOD & Audit", "method": "POST", "path": "/api/eod/save-from-last-run", "description": "Save EOD from last dashboard run", "confirm": True},
    {
        "group": "EOD & Audit",
        "method": "POST",
        "path": "/api/eod/run",
        "description": "Run full EOD snapshot (slow)",
        "query": {"force": "true", "refresh_dashboard": "true", "universe": "dashboard"},
        "confirm": True,
    },
    {"group": "EOD & Audit", "method": "GET", "path": "/api/audit/summary", "description": "Signal audit summary"},
    {"group": "EOD & Audit", "method": "GET", "path": "/api/audit/report", "description": "Audit report"},
    {"group": "EOD & Audit", "method": "GET", "path": "/api/audit/cohort", "description": "Audit cohort tickers"},
    {"group": "EOD & Audit", "method": "GET", "path": "/api/audit/breakdown", "description": "Audit breakdown by gate"},
    {"group": "EOD & Audit", "method": "GET", "path": "/api/audit/records", "description": "Audit records (paginated)"},
    {"group": "EOD & Audit", "method": "GET", "path": "/api/audit/export", "description": "Export audit CSV"},
    {"group": "EOD & Audit", "method": "POST", "path": "/api/audit/resolve", "description": "Resolve audit record", "body": {}, "confirm": True},
    # Paper & income
    {"group": "Paper & Income", "method": "GET", "path": "/api/income-book", "description": "Income book plan + proposals"},
    {
        "group": "Paper & Income",
        "method": "POST",
        "path": "/api/income-book",
        "description": "Income book action (settings/trades)",
        "body": {"action": "update_settings", "goal_usd": 5000, "capital_usd": 100000, "timeframe_months": 3},
    },
    {
        "group": "Paper & Income",
        "method": "POST",
        "path": "/api/paper-trading/purge-velocity",
        "description": "Purge velocity paper track",
        "query": {"dry_run": "true"},
        "confirm": True,
    },
    # Behavior & portfolio
    {"group": "Behavior", "method": "GET", "path": "/api/theses", "description": "Thesis storage"},
    {"group": "Behavior", "method": "GET", "path": "/api/behavior/journal", "description": "Trade journal entries"},
    {"group": "Behavior", "method": "GET", "path": "/api/behavior/cooldown/{ticker}", "description": "Trim cooldown", "path_params": {"ticker": "SPY"}},
    {
        "group": "Behavior",
        "method": "POST",
        "path": "/api/behavior/journal",
        "description": "Add journal note",
        "body": {"ticker": "SPY", "note": "Ad-hoc test entry"},
    },
    {
        "group": "Behavior",
        "method": "POST",
        "path": "/api/behavior/trim-cooldown",
        "description": "Set trim cooldown",
        "body": {"ticker": "SPY", "days": 14},
        "confirm": True,
    },
    {"group": "Behavior", "method": "POST", "path": "/api/tickers", "description": "Add watchlist ticker", "body": {"ticker": "TEST"}, "confirm": True},
    {"group": "Behavior", "method": "DELETE", "path": "/api/tickers/{ticker}", "description": "Remove watchlist ticker", "path_params": {"ticker": "TEST"}, "confirm": True},
    # Scanner & alerts
    {"group": "Scanner", "method": "GET", "path": "/api/scanner/alerts", "description": "Scanner alerts"},
    {"group": "Scanner", "method": "GET", "path": "/api/scanner/stats", "description": "Scanner stats"},
    {"group": "Scanner", "method": "GET", "path": "/api/scanner/universe", "description": "Scanner universe"},
    {"group": "Scanner", "method": "GET", "path": "/api/scanner/thresholds", "description": "Surfacing thresholds"},
    {"group": "Alerts", "method": "GET", "path": "/api/alerts/status", "description": "Alerts pipeline status"},
    {"group": "Alerts", "method": "GET", "path": "/api/alerts/feed", "description": "Alerts feed"},
    {"group": "Alerts", "method": "GET", "path": "/api/alerts/latest", "description": "Latest alerts"},
    # Push & misc
    {"group": "Other", "method": "GET", "path": "/api/public-config", "description": "Public web config"},
    {"group": "Other", "method": "POST", "path": "/api/chat", "description": "Chat copilot", "body": {"message": "Summarize SPY signal"}, "confirm": True},
    {"group": "Dev", "method": "GET", "path": "/api/dev/endpoints", "description": "This endpoint catalog"},
    {"group": "Dev", "method": "GET", "path": "/docs", "description": "FastAPI Swagger UI (new tab)", "external": True},
    {"group": "Dev", "method": "GET", "path": "/openapi.json", "description": "OpenAPI schema JSON", "external": True},
]


def get_endpoint_catalog() -> list[dict[str, Any]]:
    return list(CATALOG)
