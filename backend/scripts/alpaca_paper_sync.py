"""
Mirror data/alpha/latest_picks.json into an Alpaca **paper** account and record fills.

Dry run by default (prints the planned orders). ``--submit`` places day limit orders at
the reference price (+/- ``--slippage-bps``). Every run appends filled orders to
data/alpha/alpaca_fills.jsonl so paper fills can be compared with the backtest.

    export ALPACA_API_KEY=... ALPACA_SECRET_KEY=...
    cd backend && python scripts/alpaca_paper_sync.py            # dry run
    cd backend && python scripts/alpaca_paper_sync.py --submit   # paper orders
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from brokers.alpaca_paper import AlpacaPaperClient, alpaca_configured, plan_rebalance

ALPHA = ROOT / "data" / "alpha"


def record_fills(client: AlpacaPaperClient, path: Path) -> int:
    seen = set()
    if path.exists():
        seen = {json.loads(line)["id"] for line in path.read_text().splitlines() if line.strip()}
    new = [o for o in client.orders(status="closed", limit=500) if o.get("filled_at") and o["id"] not in seen]
    with path.open("a") as f:
        for o in new:
            f.write(json.dumps({k: o.get(k) for k in (
                "id", "client_order_id", "symbol", "side", "qty", "filled_qty", "filled_avg_price",
                "limit_price", "submitted_at", "filled_at", "status")}) + "\n")
    return len(new)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--picks", default=str(ALPHA / "latest_picks.json"))
    ap.add_argument("--submit", action="store_true")
    ap.add_argument("--slippage-bps", type=float, default=10.0)
    args = ap.parse_args()
    if not alpaca_configured():
        print("Alpaca not configured (ALPACA_API_KEY / ALPACA_SECRET_KEY) — nothing to do")
        return
    client = AlpacaPaperClient()
    picks = json.loads(Path(args.picks).read_text()).get("picks", [])
    acct = client.account()
    equity = float(acct["equity"])
    positions = {p["symbol"]: int(float(p["qty"])) for p in client.positions()}
    prices = {}
    for tk in {p["ticker"] for p in picks} | set(positions):
        bar = client.latest_bar(tk)
        if bar:
            prices[tk] = float(bar["c"])
    orders = plan_rebalance(picks, equity, prices, positions)
    print(json.dumps({"equity": equity, "orders": orders}, indent=2))
    if args.submit:
        for o in orders:
            adj = 1 + (args.slippage_bps / 1e4) * (1 if o["side"] == "buy" else -1)
            res = client.submit_order(o["symbol"], o["qty"], o["side"], limit_price=o["ref_price"] * adj)
            print(f"submitted {o['side']} {o['qty']} {o['symbol']} -> {res.get('id')} {res.get('status')}")
    ALPHA.mkdir(parents=True, exist_ok=True)
    print(f"recorded {record_fills(client, ALPHA / 'alpaca_fills.jsonl')} new fills")


if __name__ == "__main__":
    main()
