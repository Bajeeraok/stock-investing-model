"""/api/research/* — screener, rule tester, event studies. Research only: nothing here changes signals."""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger("api.research")
router = APIRouter()


class ScreenIn(BaseModel):
    rule: dict
    columns: Optional[list[str]] = None
    sort: Optional[str] = None
    desc: bool = True
    limit: int = Field(200, ge=1, le=500)
    include_etfs: bool = False
    as_of: Optional[str] = None
    universe: str = "sp500"


class BacktestIn(BaseModel):
    rule: dict
    hold_days: int = Field(20, ge=1, le=252)
    stop_pct: Optional[float] = Field(None, gt=0, lt=100)
    target_pct: Optional[float] = Field(None, gt=0, lt=1000)
    cost_bps: float = Field(10.0, ge=0, le=500)
    entry: str = "on_change"
    split_date: Optional[str] = "2019-01-01"
    start: Optional[str] = None
    end: Optional[str] = None
    include_etfs: bool = False
    label: Optional[str] = None


class EventIn(BaseModel):
    source: str
    rule: Optional[dict] = None
    tickers: Optional[list[str]] = None
    items: Optional[list[str]] = None
    kind: str = "any"
    threshold_pct: float = 5.0
    release: str = "cpi"
    pre: int = Field(5, ge=0, le=20)
    post: int = Field(20, ge=1, le=60)
    include_etfs: bool = False
    universe: str = "custom"


def _fc():
    from research import panel
    from research.integration import get_fc

    fc = get_fc()
    if fc is None:
        if panel.run_in_background("build"):
            logger.info("[research] panel missing; build started")
        raise HTTPException(503, "Research data is being built (about a minute). Try again shortly.")
    return fc


def _ours() -> list[str]:
    from research.integration import tracked_tickers

    t = tracked_tickers()
    if not t:
        raise HTTPException(503, "The tracked ticker list isn't loaded yet. Try again shortly.")
    return t


def _rule_err(e: Exception):
    raise HTTPException(400, str(e))


@router.get("/research/fields")
def fields():
    from research.dsl import NUM_OPS
    from research.features import registry_json

    return {"fields": registry_json(), "ops": list(NUM_OPS) + ["in", "not_in"]}


@router.get("/research/status")
def status():
    from research import panel

    return panel.status()


@router.post("/research/panel/refresh")
def refresh(full: bool = False):
    from research import panel

    started = panel.run_in_background("build" if full else "update")
    return {"started": started, **panel.status()}


@router.get("/research/sectors")
def sectors():
    fc = _fc()
    return {"sectors": sorted({s for t, s in fc.p.sectors.items() if s and s != "ETF"})}


@router.post("/research/screen")
def screen(body: ScreenIn):
    from research.dsl import RuleError
    from research.screener import screen as _screen

    fc = _fc()
    try:
        only = _ours() if body.universe == "ours" else None
        return _screen(fc, body.rule, body.columns, body.sort, body.desc, body.limit, body.include_etfs, body.as_of, only=only)
    except (RuleError, ValueError, KeyError) as e:
        _rule_err(e)


@router.post("/research/backtest")
def backtest(body: BacktestIn):
    from research import service
    from research.dsl import RuleError, family_key, validate
    from research.tester import backtest as _bt

    try:
        validate(body.rule)
    except RuleError as e:
        _rule_err(e)
    fc = _fc()
    params = body.model_dump(exclude={"label"})
    params["panel"] = fc.p.meta.get("built_at")
    h = service.params_hash("backtest", params)
    fam = family_key(body.rule)

    def run():
        n_prev, variants = service.family_trials(fam)
        already = any(r.get("hash") == h for r in service.read_runs() if r.get("family") == fam)
        n_trials = n_prev if already else n_prev + 1
        res = _bt(fc, body.rule, hold_days=body.hold_days, stop_pct=body.stop_pct, target_pct=body.target_pct,
                  cost_bps=body.cost_bps, entry=body.entry, split_date=body.split_date, start=body.start, end=body.end,
                  include_etfs=body.include_etfs, n_trials=n_trials, variant_months=variants or None)
        res["run"] = service.log_run(res, h, body.label) if not already else None
        return res

    return service.submit("backtest", params, run)


@router.post("/research/event-study")
def event_study(body: EventIn):
    from config_loader import load_config
    from research import service
    from research.dsl import RuleError, validate
    from research.event_study import run as _run

    if body.source == "rule":
        try:
            validate(body.rule or {})
        except RuleError as e:
            _rule_err(e)
    fc = _fc()
    kw = body.model_dump(exclude={"source", "universe"})
    if body.universe == "ours":
        kw["tickers"] = _ours()
    params = body.model_dump() | {"tickers": kw["tickers"], "panel": fc.p.meta.get("built_at")}
    return service.submit("event_study", params, lambda: _run(fc, load_config(), body.source, **kw))


@router.get("/research/jobs/{job_id}")
def job(job_id: str):
    from research import service

    j = service.get(job_id)
    if not j:
        raise HTTPException(404, "job not found (server may have restarted)")
    return j


@router.get("/research/runs")
def runs(limit: int = 100):
    from research import service

    rows = service.read_runs()
    fams: dict[str, int] = {}
    for r in rows:
        fams[r.get("family")] = fams.get(r.get("family"), 0) + 1
    from research.integration import load_approved

    approved = load_approved()
    out = [{k: v for k, v in r.items() if k != "monthly"} | {"family_runs": fams.get(r.get("family"), 0), "approved": r.get("id") in approved}
           for r in rows[-limit:]]
    return {"runs": out[::-1], "total": len(rows), "approved": len(approved)}


@router.post("/research/runs/{run_id}/approve")
def approve_run(run_id: str):
    from research.integration import approve

    try:
        return {"approved": True, **approve(run_id)}
    except KeyError:
        raise HTTPException(404, "run not found")
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.delete("/research/runs/{run_id}/approve")
def unapprove_run(run_id: str):
    from research.integration import unapprove

    return {"approved": False, "removed": unapprove(run_id)}


@router.get("/research/rule-hits")
def rule_hits(ticker: Optional[str] = None):
    from research.integration import rule_hits as _hits

    fc = _fc()
    h = _hits([ticker] if ticker else None, fc=fc)
    return {"as_of": str(fc.p.close.index[-1].date()), "hits": h}
