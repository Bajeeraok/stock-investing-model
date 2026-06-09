"""Shared SEC EDGAR helpers (identity, edgartools bootstrap)."""
from __future__ import annotations

from typing import Any

_IDENTITY_SET = False


def ensure_edgar_identity(config: dict | None = None) -> None:
    """Set SEC-required User-Agent via edgartools (once per process)."""
    global _IDENTITY_SET
    if _IDENTITY_SET:
        return
    cfg = config or {}
    inst = cfg.get("institutional") or {}
    identity = (
        inst.get("edgar_identity")
        or "ThriveAlpha/1.0 (SEC EDGAR; mailto:support@example.com)"
    )
    try:
        from edgar import set_identity

        set_identity(identity)
        _IDENTITY_SET = True
    except ImportError as exc:
        raise ImportError("edgartools not installed — pip install edgartools") from exc


def edgartools_available() -> bool:
    try:
        import edgar  # noqa: F401

        return True
    except ImportError:
        return False


def shares_for_ticker_in_report(report: Any, ticker: str, issuer_hint: str | None = None) -> int:
    """Sum 13F report holdings rows matching ticker (or issuer name hint)."""
    holdings = getattr(report, "holdings", None)
    if holdings is None or getattr(holdings, "empty", True):
        return 0
    sym = ticker.upper()
    try:
        if "Ticker" in holdings.columns:
            mask = holdings["Ticker"].fillna("").astype(str).str.upper() == sym
            if mask.any():
                return int(holdings.loc[mask, "SharesPrnAmount"].astype(float).sum())
        if issuer_hint and "Issuer" in holdings.columns:
            word = issuer_hint.split()[0]
            mask = holdings["Issuer"].fillna("").astype(str).str.contains(word, case=False, na=False)
            if mask.any():
                return int(holdings.loc[mask, "SharesPrnAmount"].astype(float).sum())
    except Exception:
        pass
    return 0
