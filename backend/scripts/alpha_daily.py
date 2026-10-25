"""
Daily alpha job: score the universe with the pooled model, build the rank-and-pick
portfolio, store features point-in-time, and write a drift report.

Outputs (data/alpha/): latest_scores.csv, latest_picks.json, drift_report.json,
pit_store/features/<date>.csv.gz. Does nothing beyond a note if no model artifact exists.

    cd backend && python scripts/alpha_daily.py --max-tickers 200
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from signals.alpha.drift import edge_decay, feature_drift, overall_status
from signals.alpha.features import SECTOR_ETF, build_panel
from signals.alpha.pit_store import PITStore
from signals.alpha.pooled_model import load_artifact, predict_latest
from signals.alpha.portfolio import rank_and_pick
from signals.alpha.universe import load_membership, members_on, sector_map
from scripts.train_alpha_model import download

OUT = ROOT / "data" / "alpha"


def _core_satellite(has_picks: bool) -> dict:
    """SPY core / regime exposure; pick weights are scaled into the satellite sleeve only."""
    from config_loader import load_config
    from signals.alpha.core_satellite import allocation, satellite_validated
    from signals.fetcher import _fetch_index_etf_history_frame

    hist = _fetch_index_etf_history_frame("SPY", "2y")
    if hist is None or hist.empty:
        return {"status": "unavailable", "satellite_pct": 0.0}
    cfg = (load_config() or {}).get("core_satellite") or {}
    return allocation(hist["Close"], satellite_validated=has_picks and satellite_validated(OUT), cfg=cfg)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=None)
    ap.add_argument("--max-tickers", type=int, default=0)
    ap.add_argument("--horizon", default="short")
    ap.add_argument("--require-promoted", action="store_true", default=True)
    ap.add_argument("--allow-unpromoted", dest="require_promoted", action="store_false")
    args = ap.parse_args()

    art = load_artifact(args.model)
    if not art:
        print("no pooled model artifact — run scripts/train_alpha_model.py first")
        return
    mem = load_membership()
    tickers = members_on(mem, pd.Timestamp.today())
    if args.max_tickers:
        tickers = tickers[: args.max_tickers]
    data = download(tickers + ["SPY"] + list(SECTOR_ETF.values()), 2)
    sectors = sector_map(mem)
    panel = build_panel(data, sector_of=sectors)
    scores = predict_latest(art, panel, require_promoted=args.require_promoted)
    OUT.mkdir(parents=True, exist_ok=True)
    scores.to_csv(OUT / "latest_scores.csv")

    prob_col = f"p_beat_{args.horizon}"
    rets = pd.DataFrame({t: d["close"].pct_change() for t, d in data.items() if t in scores.index})
    picks = rank_and_pick(scores, rets, prob_col=prob_col, sector_of=sectors) if prob_col in scores else {
        "picks": [], "note": f"{args.horizon} model not promoted — prefer SPY"}
    picks["allocation"] = _core_satellite(bool(picks.get("picks")))
    sat = float(picks["allocation"].get("satellite_pct") or 0.0) / 100
    for pk in picks.get("picks", []):
        if isinstance(pk, dict) and "weight" in pk:
            pk["portfolio_weight"] = round(float(pk["weight"]) * sat, 4)
    picks["as_of"] = scores["as_of"].iloc[0] if len(scores) else None
    picks["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    (OUT / "latest_picks.json").write_text(json.dumps(picks, indent=2, default=str))

    last = panel.index.get_level_values("date").max()
    latest_feats = panel.xs(last, level="date")
    PITStore().append("features", latest_feats.join(scores.drop(columns=["as_of"]), how="left"), last)

    hm = (art.get("horizons") or {}).get(args.horizon) or {}
    feats = hm.get("features") or []
    ref = panel[panel.index.get_level_values("date") < last - pd.Timedelta(days=90)]
    fd = feature_drift(ref.reindex(columns=feats), latest_feats.reindex(columns=feats), feats)
    report = {"as_of": str(pd.Timestamp(last).date()), "feature_psi": fd}
    tracked = ROOT / "data" / "alpha" / "tracked_picks.csv"
    if tracked.exists():
        t = pd.read_csv(tracked)
        exp = (hm.get("walk_forward_metrics") or {}).get("top_net_excess_pct") or 0.0
        report["edge_decay"] = edge_decay(t.get("excess_return_pct", pd.Series(dtype=float)), exp)
    report["status"] = overall_status(fd, report.get("edge_decay", {}))
    (OUT / "drift_report.json").write_text(json.dumps(report, indent=2, default=str))
    print(json.dumps({"picks": len(picks.get("picks", [])), "drift": report["status"]}))


if __name__ == "__main__":
    main()
