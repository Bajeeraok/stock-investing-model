"""
Insider & Institutional Flow Tracker — SEC EDGAR (free, no API key).

Form 4 filings: insider buys/sells via edgartools (primary) with legacy XML fallback.
SEC requires User-Agent identifying the application; stay under 10 requests/second.
"""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timedelta
from typing import Any
from xml.etree import ElementTree as ET

from config_loader import resolve_existing_data_file, writable_data_path

logger = logging.getLogger(__name__)

USER_AGENT = "ThriveAlpha/1.0 (Insider flow tracker; mailto:support@example.com)"

PURCHASE_CODES = {"P", "A", "G", "M"}
SALE_CODES = {"S", "D", "F"}

SEC_DATA_BASE = "https://data.sec.gov"
SEC_ARCHIVES_BASE = "https://www.sec.gov/Archives/edgar/data"
COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

TTL_TICKERS_JSON = 24 * 3600
MAX_FORM4_PER_TICKER = 5
REQUEST_DELAY = 0.12


def _sec_request(url: str) -> tuple[str | None, str | None]:
    """GET with SEC-required User-Agent. Returns (body, error)."""
    try:
        import urllib.request

        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.read().decode("utf-8", errors="replace"), None
    except Exception as e:
        return None, str(e)


def get_ticker_to_cik(tickers: list[str]) -> dict[str, str]:
    """Map ticker -> CIK (zero-padded 10 digits). Uses SEC company_tickers.json; caches to disk."""
    want = {t.upper().strip() for t in tickers if t and t.strip()}
    if not want:
        return {}
    read_path = resolve_existing_data_file("edgar_company_tickers.json")
    write_path = writable_data_path("edgar_company_tickers.json")
    now = time.time()
    cache_data: dict[str, Any] = {}
    if read_path is not None and (now - read_path.stat().st_mtime) < TTL_TICKERS_JSON:
        try:
            with open(read_path) as f:
                cache_data = json.load(f)
        except Exception:
            pass
    if not cache_data or "data" not in cache_data:
        body, err = _sec_request(COMPANY_TICKERS_URL)
        if err or not body:
            logger.debug("EDGAR company_tickers fetch failed: %s", err)
            return {}
        try:
            data = json.loads(body)
            cache_data = {"data": data, "ts": now}
            write_path.parent.mkdir(parents=True, exist_ok=True)
            with open(write_path, "w") as f:
                json.dump(cache_data, f)
        except Exception as e:
            logger.debug("EDGAR company_tickers parse failed: %s", e)
            return {}
        time.sleep(REQUEST_DELAY)
    out = {}
    raw = cache_data.get("data")
    if isinstance(raw, dict):
        for v in raw.values():
            if isinstance(v, dict):
                t = (v.get("ticker") or "").upper()
                if t in want:
                    cik = v.get("cik_str") or v.get("cik")
                    if cik is not None:
                        out[t] = str(cik).zfill(10)
    return out


def _classify_transaction(code: str, transaction_type: str) -> str:
    code_u = (code or "").strip().upper()
    ttype = (transaction_type or "").lower()
    if code_u in PURCHASE_CODES or "purchase" in ttype:
        return "buy"
    if code_u in SALE_CODES or "sale" in ttype or ttype == "sell":
        return "sell"
    return "other"


def _buys_sells_from_form4(form4: Any) -> tuple[int, int, int]:
    """Return (buy_shares, sell_shares, transaction_count) from edgartools Form4 object."""
    buys = 0
    sells = 0
    count = 0
    activities = []
    if hasattr(form4, "get_transaction_activities"):
        activities = form4.get_transaction_activities() or []
    for act in activities:
        code = getattr(act, "code", "") or ""
        ttype = getattr(act, "transaction_type", "") or ""
        try:
            shares = int(getattr(act, "shares", 0) or 0)
        except (TypeError, ValueError):
            shares = 0
        kind = _classify_transaction(code, ttype)
        count += 1
        if kind == "buy":
            buys += shares
        elif kind == "sell":
            sells += shares
    if count == 0:
        try:
            p = form4.common_stock_purchases
            if p is not None and not getattr(p, "empty", True) and "Shares" in p.columns:
                buys = int(p["Shares"].astype(float).sum())
                count += len(p)
        except Exception:
            pass
        try:
            s = form4.common_stock_sales
            if s is not None and not getattr(s, "empty", True) and "Shares" in s.columns:
                sells = int(s["Shares"].astype(float).sum())
                count += len(s)
        except Exception:
            pass
    return buys, sells, count


def _filing_edgar_url(filing: Any) -> str:
    for attr in ("homepage_url", "filing_url", "url"):
        val = getattr(filing, attr, None)
        if val:
            return str(val)
    return ""


def _run_insider_flow_edgartools(
    tickers: list[str],
    max_form4_per_ticker: int = MAX_FORM4_PER_TICKER,
    days_lookback: int | None = 90,
    config: dict | None = None,
) -> dict[str, Any]:
    from edgar import Company

    from signals.edgar_common import ensure_edgar_identity

    ensure_edgar_identity(config)
    from signals.time_et import now_et

    cutoff = None
    if days_lookback:
        cutoff = (now_et() - timedelta(days=days_lookback)).strftime("%Y-%m-%d")

    ticker_activities: list[dict] = []
    insider_buys: list[dict] = []
    insider_sells: list[dict] = []

    for ticker in tickers[:50]:
        sym = (ticker or "").upper().strip()
        if not sym:
            continue
        try:
            filings = Company(sym).get_filings(form="4")
        except Exception as exc:
            logger.debug("Form 4 filings %s: %s", sym, exc)
            continue
        if filings is None or len(filings) == 0:
            continue
        n = 0
        for filing in filings:
            if n >= max_form4_per_ticker:
                break
            fdate = str(getattr(filing, "filing_date", "") or "")[:10]
            if cutoff and fdate and fdate < cutoff:
                continue
            try:
                form4 = filing.obj()
            except Exception as exc:
                logger.debug("Form 4 parse %s %s: %s", sym, fdate, exc)
                continue
            if form4 is None:
                continue
            buys, sells, tx_count = _buys_sells_from_form4(form4)
            edgar_url = _filing_edgar_url(filing)
            ticker_activities.append({
                "ticker": sym,
                "filing_date": fdate,
                "edgar_url": edgar_url,
                "buys_shares": buys,
                "sells_shares": sells,
                "transaction_count": tx_count,
                "parser": "edgartools",
            })
            if buys > 0:
                insider_buys.append({
                    "ticker": sym,
                    "filing_date": fdate,
                    "shares": buys,
                    "edgar_url": edgar_url,
                })
            if sells > 0:
                insider_sells.append({
                    "ticker": sym,
                    "filing_date": fdate,
                    "shares": sells,
                    "edgar_url": edgar_url,
                })
            n += 1

    return {
        "ticker_activities": ticker_activities[:100],
        "insider_buys": insider_buys[:80],
        "insider_sells": insider_sells[:80],
        "message": None,
        "parser": "edgartools",
    }


# ── Legacy XML fallback (used when edgartools unavailable) ───────────────────


def get_form4_filings_for_cik(cik: str, max_filings: int = MAX_FORM4_PER_TICKER) -> list[dict]:
    url = f"{SEC_DATA_BASE}/submissions/CIK{cik}.json"
    body, err = _sec_request(url)
    if err or not body:
        return []
    time.sleep(REQUEST_DELAY)
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return []
    recent = (data.get("filings") or {}).get("recent") or {}
    forms = recent.get("form") or []
    acc = recent.get("accessionNumber") or []
    dates = recent.get("filingDate") or []
    primary = recent.get("primaryDocument") or []
    n = min(len(forms), len(acc), len(dates), len(primary))
    out = []
    for i in range(n):
        if forms[i] == "4":
            an = (acc[i] or "").replace("-", "")
            out.append({
                "accessionNumber": acc[i],
                "accessionNumberSansDashes": an,
                "filingDate": dates[i],
                "primaryDocument": primary[i] or "",
            })
            if len(out) >= max_filings:
                break
    return out


def _document_url(cik: str, accession_sans_dashes: str, primary_document: str) -> str:
    cik_int = int(cik) if cik else 0
    return f"{SEC_ARCHIVES_BASE}/{cik_int}/{accession_sans_dashes}/{primary_document}"


def _parse_form4_xml_for_transactions(xml_body: str) -> list[dict]:
    results = []
    code_pattern = re.compile(r"<[^>]*[Tt]ransaction[Cc]ode[^>]*>\s*([A-Z])\s*</", re.IGNORECASE)
    share_pattern = re.compile(r"<[^>]*[Tt]ransaction[Ss]hares[^>]*>\s*([\d.]+)\s*</", re.IGNORECASE)
    codes = code_pattern.findall(xml_body)
    shares_list = [int(float(m)) for m in share_pattern.findall(xml_body)]
    for i, code in enumerate(codes):
        shares = shares_list[i] if i < len(shares_list) else 0
        tx_type = _classify_transaction(code, "")
        results.append({"code": code, "shares": shares, "type": tx_type})
    if not results:
        try:
            root = ET.fromstring(xml_body)
            for elem in root.iter():
                tag = (elem.tag or "").split("}")[-1]
                if tag == "transactionCode" and elem.text:
                    code = elem.text.strip().upper()
                    results.append({
                        "code": code, "shares": 0,
                        "type": _classify_transaction(code, ""),
                    })
                elif tag == "transactionShares" and elem.text and results:
                    try:
                        results[-1]["shares"] = int(float(elem.text))
                    except (ValueError, TypeError):
                        pass
        except ET.ParseError:
            pass
    return results


def fetch_form4_transactions(cik: str, filing: dict) -> tuple[list[dict], str | None]:
    url = _document_url(cik, filing["accessionNumberSansDashes"], filing["primaryDocument"])
    body, err = _sec_request(url)
    if err or not body:
        return [], err or "Empty response"
    time.sleep(REQUEST_DELAY)
    return _parse_form4_xml_for_transactions(body), None


def _run_insider_flow_legacy(
    tickers: list[str],
    max_form4_per_ticker: int = MAX_FORM4_PER_TICKER,
    days_lookback: int | None = 90,
) -> dict[str, Any]:
    ticker_to_cik = get_ticker_to_cik(tickers)
    if not ticker_to_cik:
        return {
            "ticker_activities": [],
            "insider_buys": [],
            "insider_sells": [],
            "message": "Could not load SEC ticker→CIK mapping.",
            "parser": "legacy_xml",
        }
    from signals.time_et import now_et

    cutoff = None
    if days_lookback:
        cutoff = (now_et() - timedelta(days=days_lookback)).strftime("%Y-%m-%d")
    ticker_activities = []
    insider_buys = []
    insider_sells = []
    for ticker, cik in list(ticker_to_cik.items())[:50]:
        filings = get_form4_filings_for_cik(cik, max_filings=max_form4_per_ticker)
        for f in filings:
            if cutoff and (f.get("filingDate") or "") < cutoff:
                continue
            transactions, err = fetch_form4_transactions(cik, f)
            buys = sum(t["shares"] for t in transactions if t.get("type") == "buy")
            sells = sum(t["shares"] for t in transactions if t.get("type") == "sell")
            acc = f.get("accessionNumber") or ""
            primary = f.get("primaryDocument") or ""
            edgar_url = _document_url(
                cik, f.get("accessionNumberSansDashes", acc.replace("-", "")), primary,
            ) if primary else ""
            ticker_activities.append({
                "ticker": ticker,
                "filing_date": f.get("filingDate"),
                "edgar_url": edgar_url,
                "buys_shares": buys,
                "sells_shares": sells,
                "transaction_count": len(transactions),
                "parser": "legacy_xml",
            })
            if buys > 0:
                insider_buys.append({
                    "ticker": ticker,
                    "filing_date": f.get("filingDate"),
                    "shares": buys,
                    "edgar_url": edgar_url,
                })
            if sells > 0:
                insider_sells.append({
                    "ticker": ticker,
                    "filing_date": f.get("filingDate"),
                    "shares": sells,
                    "edgar_url": edgar_url,
                })
    return {
        "ticker_activities": ticker_activities[:100],
        "insider_buys": insider_buys[:80],
        "insider_sells": insider_sells[:80],
        "message": None,
        "parser": "legacy_xml",
    }


def run_insider_flow(
    tickers: list[str],
    max_form4_per_ticker: int = MAX_FORM4_PER_TICKER,
    days_lookback: int | None = 90,
    config: dict | None = None,
) -> dict[str, Any]:
    """
    For each ticker, get recent Form 4 filings and classify buys/sells.
    Uses edgartools when installed; falls back to legacy XML parsing.
    """
    try:
        from signals.edgar_common import edgartools_available

        if edgartools_available():
            return _run_insider_flow_edgartools(
                tickers,
                max_form4_per_ticker=max_form4_per_ticker,
                days_lookback=days_lookback,
                config=config,
            )
    except Exception as exc:
        logger.debug("edgartools insider flow failed, using legacy: %s", exc)
    return _run_insider_flow_legacy(
        tickers,
        max_form4_per_ticker=max_form4_per_ticker,
        days_lookback=days_lookback,
    )
