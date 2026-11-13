"""Background jobs, result cache and the research run log (every backtest is a counted trial)."""
from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
import uuid
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

logger = logging.getLogger(__name__)

_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="research")
_jobs: "OrderedDict[str, dict]" = OrderedDict()
_by_hash: dict[str, str] = {}
_log_lock = threading.Lock()
MAX_JOBS = 30
LOG_SUMMARY_KEYS = ("n", "mean", "win_rate", "worst", "vs_spy", "vs_random")


def params_hash(kind: str, params: dict) -> str:
    return hashlib.sha1(json.dumps([kind, params], sort_keys=True, default=str).encode()).hexdigest()[:16]


def submit(kind: str, params: dict, fn: Callable[[], dict]) -> dict:
    h = params_hash(kind, params)
    jid = _by_hash.get(h)
    if jid and jid in _jobs and _jobs[jid]["state"] in ("queued", "running", "done"):
        return public(_jobs[jid])
    jid = uuid.uuid4().hex[:12]
    job = {"id": jid, "kind": kind, "state": "queued", "created": time.time(), "hash": h, "params": params}
    _jobs[jid] = job
    _by_hash[h] = jid
    while len(_jobs) > MAX_JOBS:
        old_id, old = _jobs.popitem(last=False)
        _by_hash.pop(old.get("hash"), None)

    def _run():
        job["state"] = "running"
        job["started"] = time.time()
        try:
            job["result"] = fn()
            job["state"] = "done"
        except ValueError as e:
            job.update(state="error", error=str(e))
        except Exception as e:
            logger.exception("[research] %s job failed", kind)
            job.update(state="error", error=f"{type(e).__name__}: {e}")
        job["finished"] = time.time()

    _pool.submit(_run)
    return public(job)


def public(job: dict) -> dict:
    return {k: v for k, v in job.items() if k != "hash"}


def get(jid: str) -> dict | None:
    j = _jobs.get(jid)
    return public(j) if j else None


def _log_path():
    from research.panel import panel_dir

    return panel_dir() / "runs.jsonl"


def _deleted_path():
    return _log_path().with_name("runs_deleted.json")


def deleted_ids() -> set[str]:
    p = _deleted_path()
    try:
        return set(json.loads(p.read_text())) if p.exists() else set()
    except Exception:
        return set()


def delete_run(run_id: str) -> bool:
    """Hide a run from History, badges and alerts. It still counts as a try of its idea."""
    if not any(r.get("id") == run_id for r in read_runs()):
        return False
    ids = deleted_ids() | {run_id}
    _deleted_path().write_text(json.dumps(sorted(ids)))
    return True


def read_runs(limit: int | None = None, include_deleted: bool = False) -> list[dict]:
    p = _log_path()
    if not p.exists():
        return []
    gone = set() if include_deleted else deleted_ids()
    out = []
    for line in p.read_text().splitlines():
        try:
            r = json.loads(line)
        except Exception:
            continue
        if r.get("id") not in gone:
            out.append(r)
    return out[-limit:] if limit else out


def family_trials(family: str) -> tuple[int, list[dict]]:
    """(trials so far for this idea, monthly returns of its distinct earlier variants)."""
    runs = [r for r in read_runs(include_deleted=True) if r.get("family") == family]
    seen, months = set(), []
    for r in runs:
        h = r.get("hash")
        if h in seen:
            continue
        seen.add(h)
        if r.get("monthly"):
            months.append(r["monthly"])
    return len(seen), months


def log_run(result: dict, h: str, label: str | None = None) -> dict:
    oos = result.get("out_of_sample") or result.get("all") or {}
    pc = result.get("promotion") or {}
    rec = {
        "id": uuid.uuid4().hex[:10], "ts": time.time(), "hash": h, "label": label, "family": result.get("family"),
        "rule": result.get("rule"), "rule_text": result.get("rule_text"), "params": result.get("params"),
        "oos": {k: oos.get(k) for k in LOG_SUMMARY_KEYS},
        "promotion": {k: pc.get(k) for k in ("n", "mean_net_pct", "t_stat", "pbo", "passes", "fails", "n_trials")}
        | {"dsr": (pc.get("deflated_sharpe") or {}).get("dsr")},
        "portfolio": {k: (result.get("portfolio") or {}).get(k) for k in ("cagr", "spy_cagr", "max_dd", "spy_max_dd", "sharpe")},
        "monthly": result.get("monthly"),
    }
    with _log_lock:
        with _log_path().open("a") as f:
            f.write(json.dumps(rec, default=str) + "\n")
    return rec
