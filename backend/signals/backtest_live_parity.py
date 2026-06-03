"""
Causal per-bar score adjustments to align backtest with live run_daily path.

When ``backtest.apply_live_adjustments`` is true, each bar uses:
  - ``market_regime`` passed into ``composite_score`` (5-level SPY regime)
  - ``market_reversal_overlay`` delta on composite (SPY+VIX history up to bar only)

Bucket MR flip (100−score) still runs after these adjustments via ``composite_bar_score_for_backtest``.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from signals.fetcher import fetch_ohlcv_safe
from signals.market_reversal_overlay import apply_overlay_to_composite, build_market_reversal_overlay
from signals.regime import get_global_market_regime

logger = logging.getLogger(__name__)


class BacktestLiveContext:
    """Pre-loaded SPY/VIX series aligned to the backtest ticker calendar."""

    def __init__(self) -> None:
        self.enabled = False
        self.config: dict[str, Any] = {}
        self.close_spy: pd.Series | None = None
        self.vix: pd.Series | None = None
        self._mro_cache: dict[str, dict[str, Any]] = {}

    @classmethod
    def prepare(
        cls,
        template_index: pd.DatetimeIndex,
        period: str,
        config: dict | None,
    ) -> BacktestLiveContext:
        cfg = config or {}
        bt = cfg.get("backtest") or {}
        ctx = cls()
        if not bt.get("apply_live_adjustments"):
            return ctx

        ctx.enabled = True
        ctx.config = cfg
        mr_cfg = cfg.get("market_regime") or {}
        index_ticker = str(mr_cfg.get("index_ticker") or "SPY").upper()
        min_days = int(mr_cfg.get("min_days_confirm", 3))

        spy = fetch_ohlcv_safe(index_ticker, period)
        vix_raw = fetch_ohlcv_safe("^VIX", period)
        if spy is None or len(spy) < 220:
            logger.warning("backtest live parity: insufficient %s history", index_ticker)
            ctx.enabled = False
            return ctx

        spy = spy.sort_index().reindex(template_index).ffill().bfill()
        ctx.close_spy = spy
        if vix_raw is not None and len(vix_raw) >= 30:
            ctx.vix = vix_raw.sort_index().reindex(template_index).ffill().bfill()
        ctx._min_days = min_days
        return ctx

    def global_regime_at(self, bar_index: int) -> str | None:
        if not self.enabled or self.close_spy is None:
            return None
        sub = self.close_spy.iloc[: bar_index + 1]
        if len(sub.dropna()) < 200:
            return None
        return get_global_market_regime(sub, min_days_confirm=getattr(self, "_min_days", 3))

    def _mro_at(self, bar_index: int) -> dict[str, Any]:
        if not self.enabled or self.close_spy is None:
            return {"enabled": False}
        date_key = str(self.close_spy.index[bar_index])[:10]
        if date_key in self._mro_cache:
            return self._mro_cache[date_key]

        spy_sub = self.close_spy.iloc[: bar_index + 1]
        vix_sub = self.vix.iloc[: bar_index + 1] if self.vix is not None else None
        vix_last = None
        if vix_sub is not None and len(vix_sub.dropna()):
            try:
                vix_last = float(vix_sub.iloc[-1])
            except (TypeError, ValueError):
                pass

        mro_cfg = self.config.get("market_reversal_overlay") or {}
        overlay = build_market_reversal_overlay(
            self.config,
            vix=vix_last,
            real_yield=None,
            market_regime_data={},
            close_spy=spy_sub,
            vix_series=vix_sub,
        )
        self._mro_cache[date_key] = overlay
        return overlay

    def apply_live_adjustments(
        self,
        composite_buy: float,
        confluence_score: float | None,
        bar_index: int,
    ) -> tuple[float, float]:
        """Regime is applied inside composite_score; this applies MRO delta only."""
        if not self.enabled:
            base_c = float(confluence_score if confluence_score is not None else composite_buy)
            return float(composite_buy), base_c

        mro_cfg = self.config.get("market_reversal_overlay") or {}
        overlay = self._mro_at(bar_index)
        apply_adj = bool(mro_cfg.get("apply_score_adjustment", True))
        return apply_overlay_to_composite(
            composite_buy,
            confluence_score,
            overlay,
            apply_adjustment=apply_adj,
        )


def composite_with_live_parity(
    close: pd.Series,
    idx: int,
    ticker: str,
    config: dict | None,
    live_ctx: BacktestLiveContext | None,
) -> float | None:
    """Raw composite at bar with optional live regime + MRO (before MR bucket flip)."""
    from signals.indicators import composite_score
    from signals.sector_classifier import get_sector_score_bias, get_sector_weights

    subset = close.iloc[: idx + 1]
    if len(subset) < 50:
        return None
    if config is None:
        try:
            from config_loader import load_config

            config = load_config()
        except Exception:
            config = {}

    global_regime = None
    if live_ctx and live_ctx.enabled:
        global_regime = live_ctx.global_regime_at(idx)

    use_spec = bool(config.get("use_spec_regime_score", False))
    weights = get_sector_weights(ticker) if ticker else None
    sig = composite_score(
        subset,
        weights=weights,
        use_spec=use_spec,
        ticker=ticker or None,
        config=config,
        market_regime=global_regime,
    )
    raw = sig.get("composite_buy")
    if raw is None:
        return None
    conf = sig.get("confluence_score")
    if conf is None:
        conf = raw
    if live_ctx and live_ctx.enabled:
        raw, _conf = live_ctx.apply_live_adjustments(float(raw), float(conf) if conf is not None else None, idx)
    bias = get_sector_score_bias(ticker) if ticker else 0.0
    return float(np.clip(raw + bias, 0.0, 100.0))
