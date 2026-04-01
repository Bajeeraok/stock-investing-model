"""Full Phase 2 pipeline: intraday → fundamentals (optional) → setup → targets → freshness → 1m gate."""
from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import datetime
from typing import Any

from signals.bear_dampening import apply_bear_dampening

from ._constants import merge_phase2_config
from .classifier import SetupClassifier
from .freshness import SignalFreshnessChecker
from .fundamentals import FMPFundamentalGate
from .intraday import IntradayFeed
from .models import SetupSignal, SetupType
from .short_backtest import ShortTermBacktester
from .targets import PriceTargetGenerator

logger = logging.getLogger(__name__)


def _log(verbose: bool, msg: str, *args: Any) -> None:
    if args:
        logger.info(msg, *args)
    else:
        logger.info(msg)
    if verbose:
        print(msg % args if args else msg)


class ThriveAlphaPhase2:
    """
    Phase 2 pipeline for a ticker + profile.
    Pass `config` from `config_loader.load_config()` so FMP uses the same key as the rest of the app.
    """

    def __init__(self, config: dict | None = None):
        self._config = config or {}
        self._p2 = merge_phase2_config(self._config)
        self.fmp = FMPFundamentalGate(self._config)
        self.feed = IntradayFeed()
        self.classifier = SetupClassifier()
        self.targets = PriceTargetGenerator(self._p2["atr_config"])
        self.freshness = SignalFreshnessChecker()
        self.backtester = ShortTermBacktester(
            min_hit_rate_1m=float(self._p2["min_hit_rate_1m"]),
            config=self._config,
        )

    def analyze(
        self,
        ticker: str,
        fair_value: float,
        profile: str = "long_term",
        hmm_bear_pct: float = 50.0,
        interval: str = "1h",
        run_backtest: bool = True,
        verbose: bool = False,
    ) -> dict[str, Any]:
        _log(verbose, "\n" + "=" * 55)
        _log(verbose, "  THRIVE ALPHA PHASE 2 — %s [%s]", ticker, profile)
        _log(verbose, "=" * 55)

        result: dict[str, Any] = {
            "ticker": ticker,
            "profile": profile,
            "timestamp": datetime.now().isoformat(),
        }

        _log(verbose, "\n[1/5] Fetching intraday data (%s)...", interval)
        data = self.feed.fetch(ticker, interval=interval)
        if data is None:
            result["error"] = "Could not fetch intraday data"
            return result

        result["current_price"] = data.current_price
        result["atr"] = round(data.atr, 4)
        result["rsi"] = round(data.rsi, 2)
        result["vwap"] = round(data.vwap, 2)
        result["volume_ratio"] = round(data.volume_ratio, 2)
        _log(
            verbose,
            "    Price: $%.2f | ATR: %.2f | RSI: %.1f | Vol: %.1fx",
            data.current_price,
            data.atr,
            data.rsi,
            data.volume_ratio,
        )

        if profile == "long_term":
            _log(verbose, "\n[2/5] Running fundamental gate (FMP)...")
            try:
                metrics = self.fmp.fetch_metrics(ticker)
                fv_check = self.fmp.validate_fair_value(
                    ticker, fair_value, data.current_price, metrics.analyst_target
                )
                gate = self.fmp.run_fundamental_gate(metrics)
                conviction = self.fmp.compute_entry_conviction(
                    ticker, data.current_price, fair_value, gate, fv_check, profile
                )
                result["fundamental_gate"] = gate
                result["fv_validation"] = fv_check
                result["entry_conviction"] = asdict(conviction)
                _log(
                    verbose,
                    "    Gate: %s | Score: %s/100 | Action: %s | Conviction: %s",
                    gate["gate"],
                    gate["score"],
                    conviction.action,
                    conviction.conviction,
                )
            except Exception as e:
                logger.exception("FMP fundamental gate failed")
                result["fundamental_gate"] = {"error": str(e)}
        else:
            _log(verbose, "\n[2/5] Skipping fundamentals (%s profile)", profile)

        _log(verbose, "\n[3/5] Classifying setup...")
        setup_type, confidence, rationale = self.classifier.classify(data, hmm_bear_pct)
        raw_conf = float(confidence)
        conf_pct = apply_bear_dampening(
            raw_conf * 100.0,
            hmm_bear_pct,
            float(self._p2.get("observed_bear_error_band", 0.0061)),
            profile,
            bull_baseline_error=float(self._p2.get("bull_baseline_error", 0.0061)),
        )
        confidence = round(conf_pct / 100.0, 4)
        damped = profile != "long_term" and abs(conf_pct - raw_conf * 100.0) > 1e-6
        result["setup"] = {
            "type": setup_type.value,
            "confidence": confidence,
            "rationale": rationale,
            "bear_dampening_applied": damped,
        }
        _log(verbose, "    Setup: %s | Confidence: %.0f%%", setup_type.value, confidence * 100)

        _log(verbose, "\n[4/5] Generating price targets...")
        targets = self.targets.generate(data, setup_type, profile)
        result["price_targets"] = targets

        if targets and targets.get("valid"):
            signal = SetupSignal(
                ticker=ticker,
                setup_type=setup_type,
                profile=profile,
                confidence=confidence,
                entry_price=targets["entry"],
                target_1=targets["target_1"],
                target_2=targets["target_2"],
                stop=targets["stop"],
                rr_ratio=targets["rr_ratio"],
                atr=targets["atr_used"],
                rationale=rationale,
            )
            result["signal_freshness"] = self.freshness.check_signal(signal)
            _log(
                verbose,
                "    Entry: $%.2f | T1: $%.2f | T2: $%.2f | Stop: $%.2f | R:R %.1f",
                targets["entry"],
                targets["target_1"],
                targets["target_2"],
                targets["stop"],
                targets["rr_ratio"],
            )
        else:
            reason = targets.get("reason", "No setup") if targets else "No setup"
            _log(verbose, "    No valid targets — %s", reason)

        if run_backtest and profile in ("day_short", "swing"):
            _log(verbose, "\n[5/5] Running 1m backtest validation...")
            bt = self.backtester.run(ticker)
            result["backtest_1m"] = bt
            _log(
                verbose,
                "    %s | Hit rate: %.1f%% | N=%s",
                "TRUSTED" if bt["trusted"] else "NOT TRUSTED",
                (bt["hit_rate"] or 0) * 100,
                bt["n_signals"],
            )
            _log(verbose, "    %s", bt["reason"])
        else:
            _log(verbose, "\n[5/5] Backtest skipped (%s)", profile)

        _log(verbose, "\n" + "=" * 55 + "\n")
        return result
