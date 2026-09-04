"""Single source of truth for the gate/scoring "model version" tag.

Stamped onto EOD signal rows, signal_audit_store events, and paper trade records at the
point each is persisted — so win-rate/accuracy reporting can isolate the current model's
real performance instead of blending it with signals produced under earlier gate/band/
regime logic.

Bump this string whenever a change to gate thresholds, target-band math, regime
classification, or entry-mode logic would materially change what a signal snapshot
means (i.e. anything under signals/retail_action_payload.py, signals/target_bands.py,
signals/hmm_regime.py, signals/tracking_gate.py). Cosmetic/display-only changes don't
need a bump. Format is free-form but "YYYY.MM.N" (year, month, sequence within month)
keeps versions sortable and dated at a glance.

History:
- 2026.09.1 — HMM direction-blind |daily_return| feature fix + BEAR-probability floor,
  ST target-band R:R multiplier fix (stop/target no longer symmetric), gates_passed
  sync fix (flat field was clobbered to 0 by readiness_score before this), OBV
  momentum-gate marginal-pass disambiguation.
"""

from __future__ import annotations

MODEL_VERSION = "2026.09.1"
