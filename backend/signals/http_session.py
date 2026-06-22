"""Shared requests.Session — reuse TCP connections to FMP and other HTTP APIs."""
from __future__ import annotations

import threading

import requests

_session: requests.Session | None = None
_lock = threading.Lock()


def get_requests_session() -> requests.Session:
    global _session
    if _session is not None:
        return _session
    with _lock:
        if _session is None:
            _session = requests.Session()
        return _session


def close_requests_session() -> None:
    global _session
    with _lock:
        if _session is not None:
            try:
                _session.close()
            except Exception:
                pass
            _session = None
