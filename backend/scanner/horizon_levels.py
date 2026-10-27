"""
Horizon levels cache and retail-alert state for ENTRY_ZONE_ENTERED, STOP_HIT, TARGET_HIT, ML_PROB_CROSSED.
Levels are written from (1) ticker detail investor_summary, (2) daily run / dashboard via
sync_horizon_levels_from_signal_results — so the scanner has bands without opening every modal.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("scanner.horizon_levels")

LEVELS_FILENAME = "horizon_levels.json"
STATE_FILENAME = "retail_alert_state.json"
READINESS_FILENAME = "readiness_cache.json"

# Days to surface "Earnings soon" (retail quick decision)
EARNINGS_SOON_DAYS = (1, 3, 5, 7)

# ML prob threshold for "model supports add" alert
ML_PROB_CROSS_THRESHOLD = 25.0

# ST / MT / LT keys in horizon_levels.json (per-ticker nested bands)
BAND_KEYS = frozenset({"short", "medium", "long"})


def _compress_entry_zone_for_alerts(
    *,
    band_key: str,
    price: float,
    low: float,
    high: float,
) -> tuple[float, float]:
    """
    Scanner alerts should use actionable entry slices, not the full model band.
    Very wide full bands (especially long horizon) can create "always in buy zone"
    alerts that read as weak prediction quality.
    """
    if not (price > 0 and high > low > 0):
        return low, high
    width = high - low
    # Keep only the lower part of each band for entry alerts.
    # Also cap absolute width vs spot so zones stay practical.
    width_frac_by_band = {"short": 0.65, "medium": 0.45, "long": 0.30}
    max_pct_by_band = {"short": 0.12, "medium": 0.20, "long": 0.28}
    frac = width_frac_by_band.get(band_key, 0.45)
    max_pct = max_pct_by_band.get(band_key, 0.20)
    capped_width = min(width * frac, price * max_pct)
    hi = low + capped_width
    # Preserve ordering and avoid degenerate zones.
    min_pad = max(0.01, price * 0.002)
    hi = max(min(hi, high), low + min_pad)
    return round(low, 2), round(hi, 2)


def _scanner_dir(data_root: Path) -> Path:
    d = data_root / "scanner"
    d.mkdir(parents=True, exist_ok=True)
    return d


def read_horizon_levels(data_root: Path) -> dict[str, dict[str, Any]]:
    """Read ticker -> band map or legacy flat {entry_low, ...}. Empty if missing."""
    path = _scanner_dir(data_root) / LEVELS_FILENAME
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.debug("read_horizon_levels failed: %s", e)
        return {}


def write_horizon_levels(data_root: Path, levels: dict[str, dict[str, Any]]) -> None:
    """Write full horizon levels map (merge with existing or replace)."""
    path = _scanner_dir(data_root) / LEVELS_FILENAME
    try:
        path.write_text(json.dumps(levels, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning("write_horizon_levels failed: %s", e)


def normalize_ticker_levels(raw: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """
    Normalize legacy flat {entry_low, ...} to { short: {...} }.
    New format: { short: {...}, medium: {...}, long: {...} }.
    """
    if not raw or not isinstance(raw, dict):
        return {}
    if any(k in raw for k in BAND_KEYS):
        return {k: v for k, v in raw.items() if k in BAND_KEYS and isinstance(v, dict)}
    if "entry_low" in raw:
        return {"short": raw}
    return {}


def merge_horizon_band_for_ticker(
    data_root: Path,
    ticker: str,
    band_key: str,
    *,
    entry_low: float,
    entry_high: float,
    stop_loss: float,
    target: float,
    horizon_label: str,
) -> None:
    """Merge one ST/MT/LT band for a ticker (nested under short/medium/long)."""
    ticker = ticker.upper()
    bk = band_key if band_key in BAND_KEYS else "short"
    levels = read_horizon_levels(data_root)
    cur = levels.get(ticker)
    if isinstance(cur, dict) and "entry_low" in cur and not any(k in cur for k in BAND_KEYS):
        levels[ticker] = {"short": cur}
    elif not isinstance(levels.get(ticker), dict):
        levels[ticker] = {}
    entry = levels.setdefault(ticker, {})
    if not isinstance(entry, dict):
        entry = {}
        levels[ticker] = entry
    old_ticker_levels = dict(entry)  # snapshot before mutation
    new_band = {
        "entry_low": round(entry_low, 2),
        "entry_high": round(entry_high, 2),
        "stop_loss": round(stop_loss, 2),
        "target": round(target, 2),
        "horizon_label": horizon_label,
    }
    entry[bk] = new_band
    write_horizon_levels(data_root, levels)
    # Fix 4: clear stale zone-entry state when user explicitly sets new levels
    reset_zone_state_if_bands_shifted(data_root, ticker, old_ticker_levels, entry)


def merge_horizon_levels_for_ticker(
    data_root: Path,
    ticker: str,
    *,
    entry_low: float,
    entry_high: float,
    stop_loss: float,
    target: float,
    horizon_label: str = "Short-term",
) -> None:
    """Merge short-term band (backward-compatible name)."""
    merge_horizon_band_for_ticker(
        data_root,
        ticker,
        "short",
        entry_low=entry_low,
        entry_high=entry_high,
        stop_loss=stop_loss,
        target=target,
        horizon_label=horizon_label,
    )


def reset_zone_state_if_bands_shifted(
    data_root: Path,
    ticker: str,
    old_levels: dict[str, Any] | None,
    new_levels: dict[str, Any],
    *,
    shift_threshold_pct: float = 3.0,
) -> bool:
    """
    Clear `was_in_entry_zone_*` and `zone_entered_at_*` from the retail alert state
    for *ticker* when the midpoint of any band has shifted by ≥ shift_threshold_pct.

    This prevents stale zone-entry state causing edge-triggered alerts to silently
    skip the next genuine entry after the user updates their levels (e.g. post-EOD
    re-computation or modal edit).

    Returns True if state was cleared.
    """
    ticker = ticker.upper()

    def _band_midpoint(band_dict: dict) -> float | None:
        el = band_dict.get("entry_low")
        eh = band_dict.get("entry_high")
        if el and eh:
            return (float(el) + float(eh)) / 2.0
        return None

    old_norm = normalize_ticker_levels(old_levels) if old_levels else {}
    new_norm = normalize_ticker_levels(new_levels) if new_levels else {}

    shifted_keys: list[str] = []
    for bk, new_band in new_norm.items():
        new_mid = _band_midpoint(new_band)
        if new_mid is None:
            continue
        old_band = old_norm.get(bk, {})
        old_mid = _band_midpoint(old_band)
        if old_mid is None:
            # New band that didn't exist before — always reset
            shifted_keys.append(bk)
            continue
        pct_shift = abs(new_mid - old_mid) / old_mid * 100.0
        if pct_shift >= shift_threshold_pct:
            shifted_keys.append(bk)

    if not shifted_keys:
        return False

    state = read_retail_alert_state(data_root)
    ticker_st = dict(state.get(ticker) or {})
    changed = False
    for bk in shifted_keys:
        zone_key = f"was_in_entry_zone_{bk}"
        entered_key = f"zone_entered_at_{bk}"
        if zone_key in ticker_st or entered_key in ticker_st:
            ticker_st.pop(zone_key, None)
            ticker_st.pop(entered_key, None)
            changed = True
    if changed:
        state[ticker] = ticker_st
        write_retail_alert_state(data_root, state)
        logger.info(
            "reset zone state for %s (band keys: %s shifted ≥ %.1f%%)",
            ticker, shifted_keys, shift_threshold_pct,
        )
    return changed


def read_retail_alert_state(data_root: Path) -> dict[str, dict[str, Any]]:
    """Read ticker -> {was_in_entry_zone, last_price, previous_ml_prob}. Empty if missing."""
    path = _scanner_dir(data_root) / STATE_FILENAME
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.debug("read_retail_alert_state failed: %s", e)
        return {}


def write_retail_alert_state(data_root: Path, state: dict[str, dict[str, Any]]) -> None:
    """Write full retail alert state for next scan."""
    path = _scanner_dir(data_root) / STATE_FILENAME
    try:
        path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning("write_retail_alert_state failed: %s", e)


def read_ml_probs(data_root: Path) -> dict[str, float]:
    """Read ticker -> short-term ML prob (0-100). From dashboard cache if present."""
    path = _scanner_dir(data_root) / "ml_probs.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}
        return {k.upper(): float(v) for k, v in data.items() if v is not None}
    except Exception as e:
        logger.debug("read_ml_probs failed: %s", e)
        return {}


def merge_ml_prob_for_ticker(data_root: Path, ticker: str, prob_pct: float) -> None:
    """Write one ticker's short-term ML prob so scanner can fire ML_PROB_CROSSED."""
    ticker = ticker.upper()
    probs = read_ml_probs(data_root)
    probs[ticker] = round(float(prob_pct), 2)
    path = _scanner_dir(data_root) / "ml_probs.json"
    try:
        path.write_text(json.dumps(probs, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning("merge_ml_prob_for_ticker failed: %s", e)


def read_readiness_cache(data_root: Path) -> dict[str, dict[str, Any]]:
    path = _scanner_dir(data_root) / READINESS_FILENAME
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.debug("read_readiness_cache failed: %s", e)
        return {}


def merge_readiness_for_ticker(data_root: Path, ticker: str, payload: dict[str, Any]) -> None:
    ticker = ticker.upper()
    cache = read_readiness_cache(data_root)
    cache[ticker] = payload
    path = _scanner_dir(data_root) / READINESS_FILENAME
    try:
        path.write_text(json.dumps(cache, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning("merge_readiness_for_ticker failed: %s", e)


def sync_horizon_levels_from_signal_results(data_root: Path, results: list[dict]) -> int:
    """
    Populate horizon_levels.json + ml_probs.json from run_signals / dashboard rows.
    Maps st_band/mt_band/lt_band (low/high) to entry zone + stop (just below ST low) + target (band high).
    Returns number of tickers that had at least one band or ML prob written.
    """
    n_tickers = 0
    for r in results:
        if not isinstance(r, dict) or r.get("error"):
            continue
        ticker = r.get("ticker")
        if not ticker:
            continue
        try:
            p = float(r.get("close") or 0)
        except (TypeError, ValueError):
            p = 0.0
        if p <= 0:
            continue

        wrote = False

        def _one_band(band: dict | None, bk: str, label: str) -> None:
            nonlocal wrote
            if not isinstance(band, dict):
                return
            lo, hi = band.get("low"), band.get("high")
            if lo is None or hi is None:
                return
            try:
                lo_f, hi_f = float(lo), float(hi)
            except (TypeError, ValueError):
                return
            if lo_f >= hi_f:
                return
            entry_lo, entry_hi = _compress_entry_zone_for_alerts(
                band_key=bk,
                price=p,
                low=lo_f,
                high=hi_f,
            )
            pad = max(0.01, p * 0.001)
            stop_loss = round(entry_lo - pad, 2)
            merge_horizon_band_for_ticker(
                data_root,
                ticker,
                bk,
                entry_low=entry_lo,
                entry_high=entry_hi,
                stop_loss=stop_loss,
                target=round(hi_f, 2),
                horizon_label=label,
            )
            wrote = True

        _one_band(r.get("st_band"), "short", "Short-term")
        _one_band(r.get("mt_band"), "medium", "Medium-term")
        _one_band(r.get("lt_band"), "long", "Long-term")

        mlp = r.get("ml_short_prob")
        if mlp is not None:
            try:
                pv = float(mlp)
                if 0.0 <= pv <= 1.0:
                    merge_ml_prob_for_ticker(data_root, ticker, pv * 100.0)
                    wrote = True
            except (TypeError, ValueError):
                pass

        try:
            from signals.readiness_score import compute_readiness

            # Alerts must agree with the ticker detail, which gates on investor_summary.retail_action
            # (row-level go_no_go/gates_passed can say GO 4/4 while the detail says HARD LOCK 3/4).
            inv = r.get("investor_summary") if isinstance(r.get("investor_summary"), dict) else {}
            ra = inv.get("retail_action") if isinstance(inv.get("retail_action"), dict) else {}
            factors = ((inv.get("actionable_score") or {}).get("factors") or {}) if isinstance(inv.get("actionable_score"), dict) else {}
            ra_over: dict[str, Any] = {}
            if ra.get("go_no_go"):
                ra_over["go_no_go"] = ra["go_no_go"]
                ra_over["gate_cleared"] = ra["go_no_go"] == "go"
            if ra.get("entry_mode"):
                ra_over["entry_mode"] = ra["entry_mode"]
            if factors.get("gates_passed") is not None:
                ra_over["gates_passed"] = factors["gates_passed"]
                if factors.get("gates_total") is not None:
                    ra_over["gates_total"] = factors["gates_total"]
            readiness = compute_readiness({**r, **ra_over})
            payload = {**readiness}
            for k in (
                "velocity_triggered",
                "velocity_score",
                "track",
                "rvol",
                "bb_pct_b",
                "velocity_reasons",
                "gates_passed",
                "gates_total",
                "go_no_go",
                "tactical_t1",
                "tactical_t2",
                "tactical_stop",
            ):
                if r.get(k) is not None:
                    payload[k] = r.get(k)
            payload.update(ra_over)
            merge_readiness_for_ticker(data_root, ticker, payload)
            wrote = True
        except Exception:
            pass

        if wrote:
            n_tickers += 1

    return n_tickers
