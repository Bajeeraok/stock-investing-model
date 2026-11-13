"""Feature registry for the screener and rule tester. Every value on date t uses data up to t's close only."""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd

from research.panel import Panel

BENCH = "SPY"


@dataclass(frozen=True)
class Feature:
    name: str
    label: str
    group: str
    unit: str
    help: str
    fn: Callable[[Panel, "FeatureCache"], pd.DataFrame]


def _sma(c: pd.DataFrame, n: int) -> pd.DataFrame:
    return c.rolling(n, min_periods=n).mean()


def _ret(n: int):
    return lambda p, fc: (p.close / p.close.shift(n) - 1) * 100


def _dist(n: int):
    return lambda p, fc: (p.close / _sma(p.close, n) - 1) * 100


def _rsi(p: Panel, fc) -> pd.DataFrame:
    d = p.close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def _atr_pct(p: Panel, fc) -> pd.DataFrame:
    pc = p.close.shift(1)
    tr = np.maximum(p.high - p.low, np.maximum((p.high - pc).abs(), (p.low - pc).abs()))
    return tr.rolling(14, min_periods=14).mean() / p.close * 100


def _vol(p: Panel, fc) -> pd.DataFrame:
    return p.close.pct_change(fill_method=None).rolling(21, min_periods=21).std() * np.sqrt(252) * 100


def _rs_spy(n: int):
    def f(p: Panel, fc):
        r = fc.get(f"ret_{n}d")
        if BENCH not in r.columns:
            return r * np.nan
        return r.sub(r[BENCH], axis=0)
    return f


def _trend_template(p: Panel, fc) -> pd.DataFrame:
    c = p.close
    s50, s150, s200 = _sma(c, 50), _sma(c, 150), _sma(c, 200)
    hi, lo = c.rolling(252, min_periods=200).max(), c.rolling(252, min_periods=200).min()
    ok = (c > s50) & (s50 > s150) & (s150 > s200) & (s200 > s200.shift(21)) & (c >= 1.3 * lo) & (c >= 0.75 * hi)
    return ok.astype("float32").where(s200.notna())


REGISTRY: "OrderedDict[str, Feature]" = OrderedDict()


def _reg(name, label, group, unit, help, fn):
    REGISTRY[name] = Feature(name, label, group, unit, help, fn)


_reg("price", "Price", "Price", "$", "Split/dividend-adjusted close.", lambda p, fc: p.close)
for n, lbl in ((1, "1 day"), (5, "1 week"), (21, "1 month"), (63, "3 months"), (126, "6 months"), (252, "12 months")):
    _reg(f"ret_{n}d", f"Return {lbl}", "Returns", "%", f"Price change over the last {n} trading days.", _ret(n))
_reg("mom_12_1", "Momentum 12-1", "Returns", "%", "12-month return skipping the latest month (classic momentum).",
     lambda p, fc: (p.close.shift(21) / p.close.shift(252) - 1) * 100)
for n in (20, 50, 200):
    _reg(f"dist_sma{n}", f"vs {n}-day average", "Trend", "%", f"How far price is above (+) or below (-) its {n}-day average.", _dist(n))
_reg("sma50_over_200", "50-day above 200-day", "Trend", "0/1", "1 when the 50-day average is above the 200-day (golden-cross state).",
     lambda p, fc: (_sma(p.close, 50) > _sma(p.close, 200)).astype("float32").where(_sma(p.close, 200).notna()))
_reg("trend_template", "Uptrend template", "Trend", "0/1", "Minervini template: price > 50d > 150d > 200d, 200d rising, 30%+ off the low, within 25% of the high.", _trend_template)
_reg("rsi14", "RSI (14)", "Momentum", "", "Wilder RSI. Under 30 is oversold, over 70 overbought.", _rsi)
_reg("dd_52w", "From 52-week high", "Trend", "%", "Drop from the 52-week closing high (0 = at the high).",
     lambda p, fc: (p.close / p.close.rolling(252, min_periods=60).max() - 1) * 100)
_reg("up_52w_low", "Above 52-week low", "Trend", "%", "Rise from the 52-week closing low.",
     lambda p, fc: (p.close / p.close.rolling(252, min_periods=60).min() - 1) * 100)
_reg("vol_ratio", "Volume vs 50-day", "Volume", "x", "Today's volume divided by its 50-day average.",
     lambda p, fc: p.volume / p.volume.rolling(50, min_periods=20).mean())
_reg("dollar_vol_m", "Dollar volume (21d)", "Volume", "$M", "Average daily traded value, in $ millions.",
     lambda p, fc: (p.close * p.volume).rolling(21, min_periods=10).mean() / 1e6)
_reg("atr_pct", "ATR %", "Risk", "%", "Average true range (14 days) as % of price: a normal day's move.", _atr_pct)
_reg("vol_21d", "Volatility (1m, annual)", "Risk", "%", "Annualised standard deviation of daily returns over 21 days.", _vol)
_reg("gap_pct", "Gap at open", "Price", "%", "Today's open vs yesterday's close.", lambda p, fc: (p.open / p.close.shift(1) - 1) * 100)
for n, lbl in ((21, "1m"), (63, "3m"), (252, "12m")):
    _reg(f"rs_spy_{n}d", f"vs SPY {lbl}", "Relative", "pts", f"{lbl} return minus SPY's {lbl} return.", _rs_spy(n))

RANKABLE = [k for k, f in REGISTRY.items() if f.unit not in ("0/1",)]


class FeatureCache:
    """Lazy per-panel cache; keeps at most ``max_items`` feature matrices in memory."""

    def __init__(self, panel: Panel, max_items: int = 10):
        self.p = panel
        self.max = max_items
        self._c: "OrderedDict[str, pd.DataFrame]" = OrderedDict()

    def get(self, name: str) -> pd.DataFrame:
        if name in self._c:
            self._c.move_to_end(name)
            return self._c[name]
        if name.endswith("_pct_rank"):
            base = self.get(name[: -len("_pct_rank")])
            v = base.where(self.p.members).rank(axis=1, pct=True) * 100
        else:
            if name not in REGISTRY:
                raise KeyError(name)
            v = REGISTRY[name].fn(self.p, self).astype("float32")
        self._c[name] = v
        while len(self._c) > self.max:
            self._c.popitem(last=False)
        return v


def registry_json() -> list[dict]:
    return [{"name": f.name, "label": f.label, "group": f.group, "unit": f.unit, "help": f.help, "rankable": f.name in RANKABLE}
            for f in REGISTRY.values()]
