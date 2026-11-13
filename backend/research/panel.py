"""Daily OHLCV panel for every S&P 500 member since START plus the scan ETFs.

Stored as wide float32 frames (dates x tickers), one gzip pickle per field under
``<data_root>/research``. ``members`` marks the days each stock was actually in the index,
so rules only fire on point-in-time members. Delisted names missing from yfinance stay
missing; ``meta['missing']`` lists them.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

START = "2006-01-01"
FIELDS = ("open", "high", "low", "close", "volume")
CHUNK = 60
SPIKE_MOVE = 0.75
SPIKE_REVERT = 0.40
SPLIT_DRIFT = 0.005
PRE_MEMBER_DAYS = 400
POST_MEMBER_DAYS = 30
MIN_ROW_COVERAGE = 0.5
BAD_MOVE = 0.40
BAD_MOVE_DAYS = 9

_lock = threading.Lock()
_status: dict[str, Any] = {"state": "idle"}
_loaded: dict[str, Any] = {}


def panel_dir() -> Path:
    from config_loader import get_data_root

    d = get_data_root() / "research"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _etfs() -> tuple[str, ...]:
    from signals.sp500_scan import SCAN_ETFS

    return SCAN_ETFS


def universe(start: str = START) -> tuple[list[str], pd.DataFrame]:
    from signals.alpha.universe import load_membership

    m = load_membership()
    m = m[m["end_date"].isna() | (m["end_date"] >= pd.Timestamp(start))]
    tickers = sorted(set(m["ticker"]) | set(_etfs()))
    return tickers, m


def members_frame(index: pd.DatetimeIndex, columns: list[str], membership: pd.DataFrame, etfs=()) -> pd.DataFrame:
    """Boolean dates x tickers: True on days the ticker was an S&P 500 member (ETFs always True)."""
    out = pd.DataFrame(False, index=index, columns=columns)
    for r in membership.itertuples(index=False):
        if r.ticker not in out.columns:
            continue
        end = r.end_date if pd.notna(r.end_date) else index.max()
        out.loc[(index >= r.start_date) & (index <= end), r.ticker] = True
    for e in etfs:
        if e in out.columns:
            out[e] = True
    return out


def clean_spikes(close: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Blank one-day bad ticks: a >75% move that reverses >40% the next day."""
    r = close.pct_change(fill_method=None)
    fwd = r.shift(-1)
    bad = ((r > SPIKE_MOVE) & (fwd < -SPIKE_REVERT)) | ((r < -SPIKE_MOVE / 2) & (fwd > SPIKE_REVERT * 1.5))
    n = int(bad.values.sum())
    return close.mask(bad), n


def clip_to_membership(frames: dict[str, pd.DataFrame], membership: pd.DataFrame, etfs=()) -> dict[str, pd.DataFrame]:
    """Blank bars outside each stock's index windows (+400d warm-up, +30d exit room).

    Old symbols get reused (CPWR, STI, POM, MI...); yfinance then returns the new company's
    prices under the old ticker. Clipping keeps only the bars of the company that was a member.
    Also drops trailing dates where most tickers have no close yet (partial-day downloads).
    """
    close = frames["close"]
    keep = pd.DataFrame(False, index=close.index, columns=close.columns)
    for r in membership.itertuples(index=False):
        if r.ticker not in keep.columns:
            continue
        lo = r.start_date - pd.Timedelta(days=PRE_MEMBER_DAYS)
        hi = (r.end_date + pd.Timedelta(days=POST_MEMBER_DAYS)) if pd.notna(r.end_date) else close.index.max()
        keep.loc[(close.index >= lo) & (close.index <= hi), r.ticker] = True
    for e in etfs:
        if e in keep.columns:
            keep[e] = True
    out = {f: w.reindex(index=close.index, columns=close.columns).where(keep) for f, w in frames.items()}
    cov = out["close"].notna().sum(axis=1)
    full = cov.max() if len(cov) else 0
    while len(cov) and cov.iloc[-1] < MIN_ROW_COVERAGE * full:
        cov = cov.iloc[:-1]
    return {f: w.loc[cov.index] for f, w in out.items()}


def reused_symbol_suspects(close: pd.DataFrame, etfs=()) -> list[str]:
    """Tickers with 9+ days of 40%+ moves: a reused symbol or broken history, not an S&P 500 stock.
    (2008 AIG/GNW/FNMA had at most 8 such days.)"""
    r = close.pct_change(fill_method=None).abs()
    n = (r > BAD_MOVE).sum()
    return sorted(t for t in n[n >= BAD_MOVE_DAYS].index if t not in set(etfs))


def _split_download(data: pd.DataFrame, tickers: list[str]) -> dict[str, pd.DataFrame]:
    out = {}
    if data is None or data.empty:
        return out
    for t in tickers:
        try:
            df = data[t] if isinstance(data.columns, pd.MultiIndex) else data
        except KeyError:
            continue
        df = df.rename(columns=str.lower)
        if "close" not in df or df["close"].dropna().empty:
            continue
        out[t] = df
    return out


def download(tickers: list[str], start: str, progress=None) -> dict[str, pd.DataFrame]:
    import yfinance as yf

    got: dict[str, pd.DataFrame] = {}
    for i in range(0, len(tickers), CHUNK):
        chunk = tickers[i : i + CHUNK]
        for attempt in range(2):
            try:
                data = yf.download(chunk, start=start, group_by="ticker", auto_adjust=True, progress=False, threads=True)
                got.update(_split_download(data, chunk))
                break
            except Exception as e:
                logger.warning("[research-panel] chunk %d attempt %d: %s", i, attempt, e)
                time.sleep(3)
        if progress:
            progress(min(i + CHUNK, len(tickers)), len(tickers))
    return got


def frames_from_bars(bars: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    out = {}
    for f in FIELDS:
        cols = {t: df[f] for t, df in bars.items() if f in df}
        w = pd.DataFrame(cols).sort_index()
        w.index = pd.DatetimeIndex(w.index).tz_localize(None).normalize()
        w = w[~w.index.duplicated(keep="last")]
        out[f] = w.astype("float32")
    return out


def _save(frames: dict[str, pd.DataFrame], meta: dict) -> None:
    d = panel_dir()
    for f, w in frames.items():
        tmp = d / f"{f}.pkl.gz.tmp"
        w.to_pickle(tmp, compression="gzip")
        tmp.replace(d / f"{f}.pkl.gz")
    (d / "meta.json").write_text(json.dumps(meta, default=str))
    _loaded.clear()


def _finish(frames: dict[str, pd.DataFrame], tickers: list[str], spikes_prev: int = 0) -> dict:
    frames = clip_to_membership(frames, universe()[1], _etfs())
    bad = reused_symbol_suspects(frames["close"], _etfs())
    frames = {f: w.drop(columns=bad) for f, w in frames.items()}
    close, n_spikes = clean_spikes(frames["close"])
    frames["close"] = close
    have = sorted(close.columns[close.notna().any()])
    meta = {
        "built_at": pd.Timestamp.now(tz="America/New_York").isoformat(),
        "start": str(close.index.min().date()) if len(close) else None,
        "as_of": str(close.index.max().date()) if len(close) else None,
        "n_tickers": len(have),
        "n_requested": len(tickers),
        "missing": sorted(set(tickers) - set(have) - set(bad)),
        "spikes_removed": n_spikes + spikes_prev,
        "excluded_bad_history": bad,
        "etfs": list(_etfs()),
    }
    _save(frames, meta)
    return meta


def build(start: str = START, tickers: list[str] | None = None) -> dict:
    all_t, _ = universe(start)
    tickers = tickers or all_t
    _status.update(state="building", done=0, total=len(tickers), started=time.time())
    bars = download(tickers, start, progress=lambda d, n: _status.update(done=d))
    return _finish(frames_from_bars(bars), tickers)


def update(full_rebuild_after_days: int = 20) -> dict:
    """Append recent bars. Tickers whose overlap close moved (split/dividend re-adjustment) are re-pulled in full."""
    meta = read_meta()
    if not meta or not meta.get("as_of"):
        return build()
    last = pd.Timestamp(meta["as_of"])
    if (pd.Timestamp.today() - last).days > full_rebuild_after_days:
        return build()
    tickers, _ = universe()
    old = {f: _read(f) for f in FIELDS}
    _status.update(state="updating", done=0, total=len(tickers), started=time.time())
    recent = frames_from_bars(download(tickers, str((last - pd.Timedelta(days=10)).date()), progress=lambda d, n: _status.update(done=d)))
    overlap = old["close"].index.intersection(recent["close"].index)
    stale: list[str] = []
    if len(overlap):
        a = old["close"].loc[overlap].reindex(columns=recent["close"].columns)
        b = recent["close"].loc[overlap]
        drift = ((b / a) - 1).abs().max()
        stale = sorted(drift[drift > SPLIT_DRIFT].index)
    frames = {}
    for f in FIELDS:
        w = old[f].combine_first(recent[f])
        w.update(recent[f])
        frames[f] = w.astype("float32")
    if stale:
        logger.info("[research-panel] re-pulling %d re-adjusted tickers", len(stale))
        fresh = frames_from_bars(download(stale, START))
        for f in FIELDS:
            for t in fresh[f].columns:
                frames[f][t] = fresh[f][t].reindex(frames[f].index)
    m = _finish(frames, tickers, int(meta.get("spikes_removed") or 0))
    m["readjusted"] = len(stale)
    return m


def run_in_background(kind: str = "update") -> bool:
    if not _lock.acquire(blocking=False):
        return False

    def _go():
        try:
            m = build() if kind == "build" else update()
            _status.update(state="ready", finished=time.time(), error=None, last=m.get("as_of"))
            logger.info("[research-panel] %s done: %s tickers through %s", kind, m.get("n_tickers"), m.get("as_of"))
        except Exception as e:
            logger.exception("[research-panel] %s failed", kind)
            _status.update(state="error", error=str(e), finished=time.time())
        finally:
            _lock.release()

    threading.Thread(target=_go, daemon=True, name=f"research-panel-{kind}").start()
    return True


def status() -> dict:
    return {**_status, "meta": {k: v for k, v in (read_meta() or {}).items() if k != "missing"}}


def read_meta() -> dict | None:
    p = panel_dir() / "meta.json"
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def _read(f: str) -> pd.DataFrame:
    p = panel_dir() / f"{f}.pkl.gz"
    key = (f, p.stat().st_mtime)
    if key not in _loaded:
        for k in [k for k in _loaded if isinstance(k, tuple) and k[0] == f]:
            _loaded.pop(k)
        _loaded[key] = pd.read_pickle(p, compression="gzip")
    return _loaded[key]


@dataclass
class Panel:
    close: pd.DataFrame
    open: pd.DataFrame
    high: pd.DataFrame
    low: pd.DataFrame
    volume: pd.DataFrame
    members: pd.DataFrame
    sectors: dict[str, str]
    etfs: tuple[str, ...]
    meta: dict = field(default_factory=dict)

    @property
    def tickers(self) -> list[str]:
        return list(self.close.columns)


def from_frames(frames: dict[str, pd.DataFrame], membership: pd.DataFrame, etfs=(), meta: dict | None = None) -> Panel:
    close = frames["close"]
    al = {f: frames[f].reindex(index=close.index, columns=close.columns) for f in FIELDS}
    members = members_frame(close.index, list(close.columns), membership, etfs)
    sectors = {t: s for t, s in zip(membership["ticker"], membership["sector"]) if s}
    for e in etfs:
        sectors.setdefault(e, "ETF")
    return Panel(**al, members=members, sectors=sectors, etfs=tuple(etfs), meta=meta or {})


def load() -> Panel | None:
    meta = read_meta()
    if not meta:
        return None
    key = ("panel", meta.get("built_at"))
    if key in _loaded:
        return _loaded[key]
    _, membership = universe(meta.get("start") or START)
    p = from_frames({f: _read(f) for f in FIELDS}, membership, _etfs(), meta)
    for k in [k for k in _loaded if isinstance(k, tuple) and k[0] == "panel"]:
        _loaded.pop(k)
    _loaded[key] = p
    return p
