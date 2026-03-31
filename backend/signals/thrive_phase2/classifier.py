"""Setup classifier: breakout / mean-reversion / momentum."""
from __future__ import annotations

from .models import IntradayData, SetupType


class SetupClassifier:
    def classify(
        self,
        data: IntradayData,
        hmm_bear_pct: float = 50.0,
    ) -> tuple[SetupType, float, list]:
        scores = {s: 0.0 for s in SetupType}
        rationale: list[str] = []
        p = data.current_price
        atr = data.atr

        breakout_score = 0.0
        if abs(p - data.resistance) < atr:
            breakout_score += 0.30
            rationale.append(f"Price ${p:.2f} near resistance ${data.resistance:.2f}")
        if data.volume_ratio > 1.5:
            breakout_score += 0.25
            rationale.append(f"Volume {data.volume_ratio:.1f}x average — surge")
        if 55 <= data.rsi <= 72:
            breakout_score += 0.25
            rationale.append(f"RSI {data.rsi:.1f} — momentum building")
        if p > data.ma20 and p > data.ma50:
            breakout_score += 0.20
            rationale.append("Price above MA20 and MA50")
        if hmm_bear_pct > 60:
            breakout_score *= 0.6
        scores[SetupType.BREAKOUT] = breakout_score

        mr_score = 0.0
        if data.rsi < 32:
            mr_score += 0.35
            rationale.append(f"RSI {data.rsi:.1f} — oversold")
        elif data.rsi < 40:
            mr_score += 0.15
            rationale.append(f"RSI {data.rsi:.1f} — approaching oversold")
        if abs(p - data.support) < atr:
            mr_score += 0.30
            rationale.append(f"Price ${p:.2f} near support ${data.support:.2f}")
        if p < data.vwap * 0.99:
            mr_score += 0.20
            rationale.append(f"Price below VWAP ${data.vwap:.2f}")
        if data.volume_ratio < 0.7:
            mr_score += 0.15
            rationale.append("Low volume — selling exhaustion")
        if hmm_bear_pct > 60:
            mr_score *= 1.2
        scores[SetupType.MEAN_REVERSION] = min(mr_score, 1.0)

        mom_score = 0.0
        if 60 <= data.rsi <= 75:
            mom_score += 0.30
            rationale.append(f"RSI {data.rsi:.1f} — strong momentum")
        if p > data.ma20 * 1.02 and p > data.ma50 * 1.03:
            mom_score += 0.30
            rationale.append("Price trending above MAs")
        if p > data.vwap:
            mom_score += 0.20
            rationale.append("Price holding above VWAP")
        if 1.0 <= data.volume_ratio <= 1.8:
            mom_score += 0.20
            rationale.append(f"Volume {data.volume_ratio:.1f}x — sustained")
        if hmm_bear_pct > 60:
            mom_score *= 0.5
        scores[SetupType.MOMENTUM_CONTINUATION] = mom_score

        best_type = max(scores, key=scores.get)
        best_score = scores[best_type]

        if best_score < 0.45:
            return SetupType.NO_SETUP, best_score, ["No clear setup — conditions mixed"]

        return best_type, round(best_score, 3), rationale
