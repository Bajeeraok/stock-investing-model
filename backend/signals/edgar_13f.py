"""
SEC EDGAR 13F-HR institutional holdings (free, quarterly lag).

Uses edgartools to parse 13F filings. Filer CIKs resolved dynamically from Yahoo top holders.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from signals.edgar_common import ensure_edgar_identity, shares_for_ticker_in_report
from signals.edgar_filer_resolve import resolve_filers_from_yahoo_holders
from signals.edgar_insider import get_ticker_to_cik, _sec_request

logger = logging.getLogger(__name__)

TTL_13F_CACHE = 24 * 3600
MAX_FILERS_DEFAULT = 5
_CHANGE_THRESHOLD_PCT = 1.0

_CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "edgar_13f_cache"


def _shares_for_ticker(report: Any, ticker: str, issuer_hint: str | None = None) -> int:
    return shares_for_ticker_in_report(report, ticker, issuer_hint)


def _issuer_title(ticker: str) -> str | None:
    mapping = get_ticker_to_cik([ticker])
    cik = mapping.get(ticker.upper())
    if not cik:
        return None
    try:
        body, err = _sec_request(f"https://data.sec.gov/submissions/CIK{cik}.json")
        if err or not body:
            return None
        data = json.loads(body)
        return (data.get("name") or "").strip() or None
    except Exception:
        return None


def _cusip_for_ticker(report: Any, ticker: str) -> str | None:
    holdings = getattr(report, "holdings", None)
    if holdings is None or getattr(holdings, "empty", True):
        return None
    sym = ticker.upper()
    try:
        if "Ticker" not in holdings.columns or "Cusip" not in holdings.columns:
            return None
        mask = holdings["Ticker"].fillna("").astype(str).str.upper() == sym
        if not mask.any():
            return None
        val = holdings.loc[mask, "Cusip"].dropna().astype(str).head(1)
        return val.iloc[0].upper() if len(val) else None
    except Exception:
        return None


def _filer_position_change(
    ticker: str,
    filer: dict[str, Any],
    issuer_hint: str | None,
) -> dict[str, Any] | None:
    from edgar import Company

    cik = int(filer["cik"])
    name = str(filer.get("name") or cik)
    try:
        company = Company(cik)
        filings = company.get_filings(form="13F-HR")
        if filings is None or len(filings) == 0:
            return None
        report = filings[0].obj()
        if report is None or not getattr(report, "has_infotable", lambda: True)():
            return None

        cur_shares = _shares_for_ticker(report, ticker, issuer_hint)
        if cur_shares <= 0:
            return None

        prev_report = report.previous_holding_report()
        prior_shares: int | None = None
        change_pct: float | None = None
        if prev_report is not None:
            prior_shares = _shares_for_ticker(prev_report, ticker, issuer_hint)
            if prior_shares and prior_shares > 0:
                change_pct = round((cur_shares - prior_shares) / prior_shares * 100.0, 2)

        period = str(getattr(report, "report_period", "") or "")[:10] or None
        prior_period = (
            str(getattr(prev_report, "report_period", "") or "")[:10] if prev_report else None
        )

        return {
            "filer": name,
            "cik": str(cik).zfill(10),
            "shares": cur_shares,
            "prior_shares": prior_shares,
            "change_pct": change_pct,
            "period_ending": period,
            "prior_period_ending": prior_period,
            "filing_date": str(getattr(report, "filing_date", "") or "")[:10] or None,
            "filer_source": filer.get("source"),
        }
    except Exception as exc:
        logger.debug("13F filer %s (%s) failed: %s", name, cik, exc)
        return None


def _trend_from_rows(rows: list[dict]) -> tuple[str, float | None, int, int]:
    comparable = [r for r in rows if r.get("change_pct") is not None]
    if not comparable:
        return "UNKNOWN", None, 0, 0
    increasing = sum(1 for r in comparable if (r.get("change_pct") or 0) > _CHANGE_THRESHOLD_PCT)
    decreasing = sum(1 for r in comparable if (r.get("change_pct") or 0) < -_CHANGE_THRESHOLD_PCT)
    n = len(comparable)
    pct_inc = increasing / n
    if n >= 2:
        if pct_inc > 0.55:
            trend = "ACCUMULATING"
        elif pct_inc < 0.45:
            trend = "DISTRIBUTING"
        else:
            trend = "NEUTRAL"
    else:
        trend = (
            "ACCUMULATING" if increasing else
            "DISTRIBUTING" if decreasing else
            "NEUTRAL"
        )
    return trend, round(pct_inc, 3), increasing, decreasing


def resolve_cusip(ticker: str, config: dict | None = None) -> tuple[str | None, str | None]:
    """Resolve issuer CUSIP from the first sampled 13F that holds the ticker."""
    sym = (ticker or "").upper().strip()
    if not sym:
        return None, "No ticker"
    try:
        ensure_edgar_identity(config)
    except ImportError as exc:
        return None, str(exc)

    filers, _src = resolve_filers_from_yahoo_holders(None, sym, config, max_filers=3)
    for filer in filers:
        try:
            from edgar import Company

            report = Company(int(filer["cik"])).get_filings(form="13F-HR")[0].obj()
            cusip = _cusip_for_ticker(report, sym)
            if cusip:
                return cusip, None
        except Exception:
            continue
    return None, f"CUSIP not found in sampled 13F filings for {sym}"


def _snapshot_cache_path(ticker: str) -> Path:
    return _CACHE_DIR / f"snapshot_{ticker.upper()}.json"


def fetch_edgar_13f_snapshot(
    ticker: str,
    *,
    use_cache: bool = True,
    config: dict | None = None,
    top_holders: list[dict] | None = None,
    allow_live_fetch: bool | None = None,
) -> dict[str, Any]:
    """
    Quarterly 13F holder-change snapshot via edgartools.

    Resolves filer CIKs from Yahoo top_holders (dynamic), then compares each filer's
    latest 13F vs previous quarter for the target ticker.
    """
    sym = (ticker or "").upper().strip()
    if not sym:
        return {"error": "No ticker", "source": "sec_edgar_13f"}

    cache_path = _snapshot_cache_path(sym)
    if use_cache and cache_path.exists():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            if time.time() - float(cached.get("ts", 0)) <= TTL_13F_CACHE:
                out = dict(cached.get("payload") or {})
                out["from_cache"] = True
                return out
        except Exception:
            pass

    cfg = config or {}
    inst_cfg = cfg.get("institutional") or {}
    live_ok = inst_cfg.get("edgar_13f_live_on_request", True) if allow_live_fetch is None else allow_live_fetch
    if not live_ok:
        return {
            "ticker": sym,
            "source": "sec_edgar_13f",
            "trend": "UNKNOWN",
            "skipped_live": True,
            "source_note": "13F live fetch skipped (cache miss). Yahoo holder trend still available.",
            "error": None,
        }

    timeout_sec = float(inst_cfg.get("edgar_13f_live_timeout_sec") or 25.0)

    def _live_fetch() -> dict[str, Any]:
        return _fetch_edgar_13f_live(sym, config=config, top_holders=top_holders)

    try:
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

        with ThreadPoolExecutor(max_workers=1) as pool:
            fut = pool.submit(_live_fetch)
            try:
                return fut.result(timeout=timeout_sec)
            except FuturesTimeout:
                logger.warning("13F live fetch timed out for %s after %.0fs", sym, timeout_sec)
                return {
                    "ticker": sym,
                    "source": "sec_edgar_13f",
                    "trend": "UNKNOWN",
                    "timed_out": True,
                    "source_note": "13F fetch timed out — retry later (results cache 24h once built).",
                    "error": f"Timed out after {timeout_sec:.0f}s",
                }
    except Exception as exc:
        logger.debug("13F fetch failed for %s: %s", sym, exc)
        return {"ticker": sym, "error": str(exc), "source": "sec_edgar_13f", "trend": "UNKNOWN"}


def _fetch_edgar_13f_live(
    sym: str,
    *,
    config: dict | None = None,
    top_holders: list[dict] | None = None,
) -> dict[str, Any]:
    try:
        ensure_edgar_identity(config)
    except ImportError as exc:
        return {"ticker": sym, "error": str(exc), "source": "sec_edgar_13f"}

    cfg = config or {}
    inst_cfg = cfg.get("institutional") or {}
    max_filers = int(inst_cfg.get("edgar_13f_max_filers") or MAX_FILERS_DEFAULT)

    if top_holders is None:
        try:
            from signals.yahoo_institutional import fetch_yahoo_institutional

            yahoo = fetch_yahoo_institutional(sym, use_cache=True)
            top_holders = yahoo.get("top_holders") or []
        except Exception:
            top_holders = []

    filers, filer_resolution = resolve_filers_from_yahoo_holders(
        top_holders, sym, config, max_filers=max_filers,
    )
    issuer_hint = _issuer_title(sym)

    filer_rows: list[dict] = []
    filings_analyzed = 0
    resolved_cusip: str | None = None
    period_ending: str | None = None
    prior_period_ending: str | None = None

    for filer in filers:
        row = _filer_position_change(sym, filer, issuer_hint)
        filings_analyzed += 2 if row else 0
        if not row:
            continue
        filer_rows.append(row)
        if not period_ending and row.get("period_ending"):
            period_ending = row["period_ending"]
        if row.get("prior_period_ending"):
            prior_period_ending = row["prior_period_ending"]
        if not resolved_cusip:
            try:
                from edgar import Company

                report = Company(int(filer["cik"])).get_filings(form="13F-HR")[0].obj()
                resolved_cusip = _cusip_for_ticker(report, sym)
            except Exception:
                pass

    trend, pct_inc, _inc, _dec = _trend_from_rows(filer_rows)
    comparable = sum(1 for r in filer_rows if r.get("change_pct") is not None)

    payload: dict[str, Any] = {
        "ticker": sym,
        "cusip": resolved_cusip,
        "source": "sec_edgar_13f",
        "source_note": "Top-holder changes from SEC 13F-HR via edgartools (quarterly, ~45d lag)",
        "parser": "edgartools",
        "filer_resolution": filer_resolution,
        "filers_resolved": [{"name": f.get("name"), "cik": f.get("cik"), "source": f.get("source")} for f in filers],
        "period_ending": period_ending,
        "prior_period_ending": prior_period_ending,
        "trend": trend,
        "pct_filings_increasing": pct_inc,
        "filers_sampled": len(filer_rows),
        "filers_comparable": comparable,
        "top_holder_changes": sorted(
            [r for r in filer_rows if r.get("change_pct") is not None],
            key=lambda x: abs(x.get("change_pct") or 0),
            reverse=True,
        )[:8],
        "filings_analyzed": filings_analyzed,
        "from_cache": False,
    }
    if not filer_rows:
        payload["error"] = "No 13F positions found for ticker in sampled filers"

    cache_path = _snapshot_cache_path(sym)
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps({"ts": time.time(), "payload": payload}, default=str),
            encoding="utf-8",
        )
    except Exception as exc:
        logger.debug("13f cache write failed: %s", exc)
    return payload
