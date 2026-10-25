"""
Batch score backtest: the live-parity composite (same path as backtest_simple.run_backtest
with backtest.apply_live_adjustments) recomputed causally every --step bars for every
S&P 500 member over --years, pooled and compared with SPY.

    cd backend && python scripts/batch_score_backtest.py --years 10 --workers 8
    cd backend && python scripts/batch_score_backtest.py --analyze-only

Writes data/alpha/score_backtest/{samples.csv.gz,report.json}. Only (date, ticker) rows
where the ticker was an index member on that date are kept (data/universe/sp500_membership.csv).
Delisted names without free price history drop out, so some survivorship bias remains.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import warnings
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

from signals.alpha.score_backtest import analyze

OUT_DIR = ROOT / "data" / "alpha" / "score_backtest"
HORIZONS = [21, 63, 126]

_W: dict = {}


def _worker_init(years: int) -> None:
    warnings.filterwarnings("ignore")
    logging.disable(logging.WARNING)
    from config_loader import load_config
    from signals.fetcher import fetch_ohlcv_safe

    _W["cfg"] = load_config()
    _W["period"] = f"{years}y"
    spy = fetch_ohlcv_safe("SPY", _W["period"])
    _W["spy"] = spy.sort_index() if spy is not None else None


def _score_ticker(ticker: str, step: int, ranges: list[tuple[str, str | None]], sector: str) -> list[dict]:
    import signals.indicators as ind
    from signals.backtest_live_parity import BacktestLiveContext, composite_with_live_parity
    from signals.fetcher import fetch_ohlcv_safe
    from signals.score_interpretation import detect_interpretation_style

    cfg, spy = _W["cfg"], _W["spy"]
    close = fetch_ohlcv_safe(ticker, _W["period"])
    if close is None or spy is None or len(close) < 300:
        return []
    close = close.sort_index()
    close = close[~close.index.duplicated()]
    ctx = BacktestLiveContext.prepare(close.index, _W["period"], cfg)
    spy_al = spy.reindex(close.index).ffill()
    spy_ma = spy_al.rolling(200).mean()
    ic = (cfg.get("score") or {}).get("interpretation") or {}
    flip_on = ic.get("apply_to_backtest_buckets", True)

    captured: dict = {}
    orig = ind.composite_score

    def _capture(*a, **k):
        r = orig(*a, **k)
        captured.clear()
        captured.update(r)
        return r

    ind.composite_score = _capture
    rows: list[dict] = []
    try:
        idx = close.index
        for i in range(260, len(close), step):
            d = idx[i]
            ds = d.strftime("%Y-%m-%d")
            if not any(s <= ds and (e is None or ds <= e) for s, e in ranges):
                continue
            raw = composite_with_live_parity(close, i, ticker, cfg, ctx)
            if raw is None:
                continue
            style = "TRENDING"
            if flip_on:
                try:
                    style = detect_interpretation_style(
                        close.iloc[: i + 1], None, cfg, ticker=ticker, for_backtest_buckets=True
                    )[0]
                except Exception:
                    pass
            score = 100.0 - raw if style == "MEAN_REVERTING" else raw
            p0, b0 = float(close.iloc[i]), float(spy_al.iloc[i])
            ma = spy_ma.iloc[i]
            row = {
                "as_of_date": ds,
                "ticker": ticker,
                "sector": sector or "Unknown",
                "score": round(float(score), 2),
                "score_raw": round(float(raw), 2),
                "style": style,
                "spy_regime": "unknown" if ma != ma else ("bull" if b0 > ma else "bear"),
                "trend_score": captured.get("trend_score"),
                "rsi_contrib": captured.get("rsi_contrib"),
                "macd_contrib": captured.get("macd_contrib"),
            }
            for h in HORIZONS:
                j = i + h
                if j < len(close) and p0 > 0 and b0 > 0:
                    r = float(close.iloc[j]) / p0 - 1
                    b = float(spy_al.iloc[j]) / b0 - 1
                    row[f"ret_{h}"] = round(100 * r, 4)
                    row[f"excess_{h}"] = round(100 * (r - b), 4)
            rows.append(row)
    finally:
        ind.composite_score = orig
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--years", type=int, default=10)
    ap.add_argument("--step", type=int, default=5, help="Score every N trading days")
    ap.add_argument("--max-tickers", type=int, default=0)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--cost-pct", type=float, default=0.30)
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    ap.add_argument("--analyze-only", action="store_true")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    samples_path = out_dir / "samples.csv.gz"

    if not args.analyze_only:
        from signals.alpha.universe import load_membership

        mem = load_membership()
        start = (pd.Timestamp.today() - pd.DateOffset(years=args.years)).strftime("%Y-%m-%d")
        mem = mem[mem["end_date"].isna() | (mem["end_date"].astype(str) >= start)]
        ranges: dict[str, list] = {}
        sector: dict[str, str] = {}
        for r in mem.itertuples():
            e = None if pd.isna(r.end_date) or not str(r.end_date) else str(r.end_date)[:10]
            ranges.setdefault(r.ticker, []).append((str(r.start_date)[:10], e))
            if isinstance(getattr(r, "sector", None), str) and r.sector:
                sector[r.ticker] = r.sector
        tickers = sorted(ranges)
        if args.max_tickers:
            rng = np.random.default_rng(0)
            tickers = sorted(rng.choice(tickers, size=min(args.max_tickers, len(tickers)), replace=False))
        print(f"{len(tickers)} tickers, {args.years}y, step {args.step}", flush=True)

        rows: list[dict] = []
        done = empty = 0
        with ProcessPoolExecutor(args.workers, initializer=_worker_init, initargs=(args.years,)) as ex:
            futs = {ex.submit(_score_ticker, t, args.step, ranges[t], sector.get(t, "")): t for t in tickers}
            for f in as_completed(futs):
                done += 1
                try:
                    res = f.result()
                except Exception as e:
                    res = []
                    print(f"{futs[f]}: {e}", flush=True)
                empty += not res
                rows.extend(res)
                if done % 25 == 0:
                    print(f"{done}/{len(tickers)} done, {empty} without data, {len(rows)} samples", flush=True)
        pd.DataFrame(rows).to_csv(samples_path, index=False, compression="gzip")
        print(f"{len(rows)} samples from {done - empty} tickers -> {samples_path}", flush=True)

    df = pd.read_csv(samples_path)
    report = analyze(df, HORIZONS, args.step, args.cost_pct)
    (out_dir / "report.json").write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    print(f"report -> {out_dir / 'report.json'}")


if __name__ == "__main__":
    main()
