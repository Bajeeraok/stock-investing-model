"""
Insider & Institutional Flow Tracker — SEC EDGAR (free, no API key).
Form 4 filings: insider buys/sells. Flags when an insider at a watched ticker buys shares.
Uses data.sec.gov (company tickers, submissions) and Archives for Form 4 documents.
SEC requires User-Agent identifying the application; stay under 10 requests/second.
"""
from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

logger = logging.getLogger(__name__)

# SEC requires User-Agent; use app name + contact
USER_AGENT = "ThriveAlpha/1.0 (Insider flow tracker; mailto:support@example.com)"

# Transaction codes: P = purchase, S = sale (open market). Others: G = gift, A = grant, etc.
PURCHASE_CODES = {"P", "A", "G", "M"}  # P=open market purchase; A=grant; G=gift; M=exercise
SALE_CODES = {"S", "D", "F"}  # S=open market sale; D=disposition; F=tax

SEC_DATA_BASE = "https://data.sec.gov"
SEC_ARCHIVES_BASE = "https://www.sec.gov/Archives/edgar/data"
COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

# Cache TTLs (seconds)
TTL_TICKERS_JSON = 24 * 3600
TTL_SUBMISSIONS = 12 * 3600
TTL_FORM4_DOC = 6 * 3600
MAX_FORM4_PER_TICKER = 5
REQUEST_DELAY = 0.12  # ~8 req/s to stay under 10


def _sec_request(url: str) -> tuple[str | None, str | None]:
    """GET with SEC-required User-Agent. Returns (body, error)."""
    try:
        import urllib.request
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.read().decode("utf-8", errors="replace"), None
    except Exception as e:
        return None, str(e)


def _tickers_path() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / "edgar_company_tickers.json"


def get_ticker_to_cik(tickers: list[str]) -> dict[str, str]:
    """
    Map ticker -> CIK (zero-padded 10 digits). Uses SEC company_tickers.json; caches to disk.
    """
    want = {t.upper().strip() for t in tickers if t and t.strip()}
    if not want:
        return {}
    cache_path = _tickers_path()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    now = time.time()
    cache_data: dict[str, Any] = {}
    if cache_path.exists() and (now - cache_path.stat().st_mtime) < TTL_TICKERS_JSON:
        try:
            with open(cache_path) as f:
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
            with open(cache_path, "w") as f:
                json.dump(cache_data, f)
        except Exception as e:
            logger.debug("EDGAR company_tickers parse failed: %s", e)
            return {}
        time.sleep(REQUEST_DELAY)
    # company_tickers.json format: {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}, ...}
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


def _submissions_url(cik: str) -> str:
    return f"{SEC_DATA_BASE}/submissions/CIK{cik}.json"


def get_form4_filings_for_cik(cik: str, max_filings: int = MAX_FORM4_PER_TICKER) -> list[dict]:
    """Fetch submissions for CIK and return list of Form 4 filing info (accessionNumber, filingDate, primaryDocument)."""
    url = _submissions_url(cik)
    body, err = _sec_request(url)
    if err or not body:
        logger.debug("EDGAR submissions %s failed: %s", cik, err)
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
            # accessionNumber has dashes; we need sans-dashes for URL
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
    # SEC path: /Archives/edgar/data/{cik_int}/{accession_no_dashes}/{filename}
    cik_int = int(cik) if cik else 0
    return f"{SEC_ARCHIVES_BASE}/{cik_int}/{accession_sans_dashes}/{primary_document}"


def _parse_form4_xml_for_transactions(xml_body: str) -> list[dict]:
    """
    Parse Form 4 XML for transactions: transactionCode, transactionShares.
    Returns list of {code, shares, type: 'buy'|'sell'}. Regex-first for namespace robustness.
    """
    results = []
    code_pattern = re.compile(r"<[^>]*[Tt]ransaction[Cc]ode[^>]*>\s*([A-Z])\s*</", re.IGNORECASE)
    share_pattern = re.compile(r"<[^>]*[Tt]ransaction[Ss]hares[^>]*>\s*([\d.]+)\s*</", re.IGNORECASE)
    codes = code_pattern.findall(xml_body)
    shares_list = [int(float(m)) for m in share_pattern.findall(xml_body)]
    for i, code in enumerate(codes):
        shares = shares_list[i] if i < len(shares_list) else 0
        tx_type = "buy" if code in PURCHASE_CODES else ("sell" if code in SALE_CODES else "other")
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
                        "type": "buy" if code in PURCHASE_CODES else ("sell" if code in SALE_CODES else "other"),
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
    """
    Fetch one Form 4 document and parse transactions. Returns (list of {code, shares, type}, error).
    """
    url = _document_url(cik, filing["accessionNumberSansDashes"], filing["primaryDocument"])
    body, err = _sec_request(url)
    if err or not body:
        return [], err or "Empty response"
    time.sleep(REQUEST_DELAY)
    transactions = _parse_form4_xml_for_transactions(body)
    return transactions, None


def run_insider_flow(
    tickers: list[str],
    max_form4_per_ticker: int = MAX_FORM4_PER_TICKER,
    days_lookback: int | None = 90,
) -> dict[str, Any]:
    """
    For each ticker, get recent Form 4 filings and classify buys/sells.
    Returns:
      ticker_activities: list of {ticker, filing_date, edgar_url, buys_shares, sells_shares, transactions}
      insider_buys: list of {ticker, filing_date, shares, edgar_url} for quick "insider bought" flags
      message: optional error/summary
    """
    ticker_to_cik = get_ticker_to_cik(tickers)
    if not ticker_to_cik:
        return {
            "ticker_activities": [],
            "insider_buys": [],
            "insider_sells": [],
            "message": "Could not load SEC ticker→CIK mapping.",
        }
    from datetime import datetime, timedelta
    cutoff = None
    if days_lookback:
        cutoff = (datetime.utcnow() - timedelta(days=days_lookback)).strftime("%Y-%m-%d")
    ticker_activities = []
    insider_buys = []
    insider_sells = []
    for ticker, cik in list(ticker_to_cik.items())[:50]:  # cap tickers to avoid timeout
        filings = get_form4_filings_for_cik(cik, max_filings=max_form4_per_ticker)
        for f in filings:
            if cutoff and (f.get("filingDate") or "") < cutoff:
                continue
            transactions, err = fetch_form4_transactions(cik, f)
            buys = sum(t["shares"] for t in transactions if t.get("type") == "buy")
            sells = sum(t["shares"] for t in transactions if t.get("type") == "sell")
            acc = f.get("accessionNumber") or ""
            primary = f.get("primaryDocument") or ""
            edgar_url = _document_url(cik, f.get("accessionNumberSansDashes", acc.replace("-", "")), primary) if primary else ""
            ticker_activities.append({
                "ticker": ticker,
                "filing_date": f.get("filingDate"),
                "edgar_url": edgar_url,
                "buys_shares": buys,
                "sells_shares": sells,
                "transaction_count": len(transactions),
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
    }
