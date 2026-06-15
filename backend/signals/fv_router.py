"""
fv_router.py — Method routing for fair value estimation.

Implements the method-routing taxonomy from valuation-edge-cases.md:

  §0  Divergence trigger  — |NTM_EPS - TTM_EPS| / max(|TTM_EPS|, ε) > 0.40
                             → switch to forward_pe regardless of TTM PE bucket
  §4  Earnings-base distortions — near-zero EPS crossover, negative TTM EPS,
                             data-sanity gate for corporate actions / <8 quarters
  §5  Sector-wrong-metric — REITs (P/FFO), Banks (P/TBV), pre-revenue biotech
  §6  Special situations   — crypto-correlated, China ADRs, recent spinoffs,
                             acquisition targets (suppress FV + momentum)

Design: pure functions, no I/O.  Call `route_fair_value()` before invoking
`estimate_fair_value()` in fair_value_estimator.py and in ticker_detail.py.

If routing returns `fv_suppressed=True`, callers should:
  - Skip `estimate_fair_value()` (or accept None FV)
  - Show badge `FV UNAVAILABLE — <fv_suppressed_reason>`
  - Still show street consensus and house tiers

If routing returns `forced_method`, callers should:
  - Pass that method hint to `estimate_fair_value()` via `force_forward_pe=True`
  - Surface the method label in the UI per §8
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


# ── §6 static flag tables ─────────────────────────────────────────────────────

# Crypto-correlated — earnings are a BTC/ETH derivative; PE-based FV meaningless.
_CRYPTO_CORRELATED: frozenset[str] = frozenset({
    "COIN", "MSTR", "MARA", "RIOT", "CLSK", "WULF", "HUT", "BITF", "BTBT", "IREN",
})

# China ADRs — multiple compressed by geopolitical/regulatory discount.
# "Cheap vs sector" is structural, not opportunity.  Cap bullishness.
_CHINA_ADRS: frozenset[str] = frozenset({
    "BABA", "PDD", "NIO", "JD", "BIDU", "KWEB", "XPEV", "LI", "BILI", "EDU",
    "TAL", "GSX", "IQ", "NTES", "WB", "VNET", "CAN", "TIGR",
})

# Recent spinoffs with known stub / restated history.
# Data-sanity gate: if TTM EPS history < 4 clean quarters → suppress Model FV.
_RECENT_SPINOFFS: frozenset[str] = frozenset({
    "SNDK", "GEV", "SOLV", "KVUE", "GEHC", "SW", "GFAI",
})

# ── §5 sector-wrong-metric tables ─────────────────────────────────────────────

# REITs: P/E destroys value via depreciation. Must use P/FFO or P/AFFO.
_REITS: frozenset[str] = frozenset({
    "O", "PLD", "AMT", "SPG", "VICI", "SBAC", "CCI", "EQR", "AVB", "PSA",
    "WPC", "VNO", "SLG", "KIM", "BXP", "IRM", "DLR", "EQIX", "NNN", "STAG",
    "MPW", "OHI", "CTRE", "LTC", "SKT", "COLD", "REXR", "FR", "EGP",
})

# Banks / financial holding cos — P/TBV vs ROTE is more appropriate than P/E vs sector.
_BANKS: frozenset[str] = frozenset({
    "JPM", "BAC", "WFC", "C", "GS", "MS", "USB", "PNC", "TFC", "SCHW",
    "BK", "STT", "NTRS", "FITB", "KEY", "RF", "HBAN", "MTB", "CFG", "CMA",
    "ZION", "WAL", "EWBC", "PACW", "FRC", "SIVB",
})

# Asset managers / alt managers — fee-based earnings; P/E vs tech sector is misleading.
_ASSET_MANAGERS: frozenset[str] = frozenset({
    "BLK", "BX", "KKR", "APO", "CG", "BEN", "IVZ", "TROW", "AMG", "APAM",
    "OWL", "STEP", "HLNE", "ARES", "TPG", "BAM", "FHI", "JHG", "VCTR", "AB",
    "MORN", "SEIC",
})

# Insurers — P/B vs ROE (normalize BRK.B → BRK-B before lookup)
_INSURERS: frozenset[str] = frozenset({
    "BRK-B", "PGR", "ALL", "AIG", "MET", "PRU", "LNC", "AFL", "UNM",
    "TRV", "CB", "HIG", "WRB", "RNR", "AWH",
})

# MLPs / midstream — EV/EBITDA + distribution coverage
_MLPS: frozenset[str] = frozenset({
    "EPD", "ET", "KMI", "MMP", "PAA", "WES", "MPLX", "DCP", "AM",
})

# Pre-revenue biotech — pipeline/cash-runway only; PE meaningless.
_PREBIOTECH: frozenset[str] = frozenset({
    "MRNA", "NVAX", "BNTX", "VRTX", "BLUE", "FATE", "EDIT", "NTLA",
    "CRSP", "BEAM", "AGEN", "IMVT", "ALDX", "APLD", "ALLK", "ARCT",
})

# Broad index ETFs / ETF asset allocation — FV from yield model, not PE-relative
_ETF_BROAD_INDEX: frozenset[str] = frozenset({
    "SPY", "QQQ", "IWM", "DIA", "VOO", "VTI", "IVV", "RSP", "ONEQ",
})

# Commodity / metal ETFs — no earnings-based FV; use technical anchor (§5)
_COMMODITY_METAL_ETFS: frozenset[str] = frozenset({
    "GLD", "IAU", "SGOL", "GLDM", "BAR", "OUNZ", "SLV", "SIL", "PSLV", "USO", "GDX", "GDXJ",
})

# ── §1 deep cyclicals — always route to forward_pe regardless of TTM PE ──────

_DEEP_CYCLICALS: frozenset[str] = frozenset({
    # Memory semis
    "MU", "SNDK", "WDC", "STX",
    # Analog / auto semis (mild cycle)
    "ON", "MCHP",
    # Airlines
    "DAL", "UAL", "AAL", "LUV", "JBLU", "SAVE", "HA",
    # E&P / oil & gas
    "OXY", "DVN", "FANG", "APA", "HAL", "SLB", "BKR",
    # Refiners
    "VLO", "MPC", "PSX",
    # Steel / materials
    "X", "CLF", "NUE", "FCX", "AA", "STLD",
    # Homebuilders
    "DHI", "LEN", "PHM", "TOL", "MDC", "KBH",
    # Chemicals
    "DOW", "LYB", "DD", "EMN",
    # Autos
    "F", "GM",
    # Shipping / tankers
    "ZIM", "FRO", "STNG",
})

# ── §2 hypergrowth secular — handled by divergence trigger dynamically ────────
# No static table needed; the 40% NTM/TTM divergence check catches them.

# ── Near-zero EPS threshold (§4) ──────────────────────────────────────────────
# P/E on $0.10 EPS is noise → route to street-only or EV/S
_NEAR_ZERO_EPS_THRESHOLD = 0.30   # absolute EPS; P/E > 200× on this → meaningless

# ── Divergence trigger threshold (§0) ─────────────────────────────────────────
_DIVERGENCE_TRIGGER_PCT = 40.0    # |NTM - TTM| / max(|TTM|, ε) > 0.40 → forward method

# ── ADR geopolitical discount cap ─────────────────────────────────────────────
# When present, we do NOT suppress but set a note to cap any implied buy signal.
# The FV is still computed; the router surfaces the "geopolitical discount" note.


# ══════════════════════════════════════════════════════════════════════════════
# RESULT DATACLASS
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class FvRoute:
    """
    Routing decision returned by `route_fair_value()`.

    Primary outcome flags:
      fv_suppressed       — True → skip FV computation; surface `fv_suppressed_reason` instead
      force_forward_pe    — True → caller should use forward_pe-based method even for low-TTM-PE names
      suppress_momentum   — True → suppress buy/momentum signals (acquisition target, imminent event)

    Metadata for UI (§8):
      method_label        — human-readable method name for the UI (replaces generic "peg_blend")
      gap_badge_type      — "METHOD" (fixable) or "OPINION" (model vs street disagreement = alpha)
      notes               — list of transparency notes shown in the model section
      geopolitical_cap    — True for China ADRs: cap implied buy signal bullishness
      is_deep_cyclical    — True when deep-cyclical override applied (§1)
      is_sector_override  — True when sector metric mismatch overrides method (§5)
      divergence_pct      — computed NTM/TTM divergence (§0) if EPS values available
    """
    # Primary outcome
    fv_suppressed: bool = False
    fv_suppressed_reason: str = ""
    force_forward_pe: bool = False
    suppress_momentum: bool = False

    # UI metadata
    method_label: str = "peg_blend"
    gap_badge_type: str = "METHOD"       # "METHOD" | "OPINION"
    notes: list[str] = field(default_factory=list)
    geopolitical_cap: bool = False
    is_deep_cyclical: bool = False
    is_sector_override: bool = False
    divergence_pct: Optional[float] = None


def _calc_divergence(ttm_eps: Optional[float], ntm_eps: Optional[float]) -> Optional[float]:
    """§0: compute |NTM - TTM| / max(|TTM|, 0.01)."""
    if ttm_eps is None or ntm_eps is None:
        return None
    denom = max(abs(float(ttm_eps)), 0.01)
    return abs(float(ntm_eps) - float(ttm_eps)) / denom * 100.0


def normalize_ticker_key(ticker: str) -> str:
    """Uppercase ticker for static-set lookups; dots → hyphens (BRK.B → BRK-B)."""
    t = str(ticker or "").upper().strip()
    return t.replace(".", "-")


def is_recent_spinoff(ticker: str) -> bool:
    return normalize_ticker_key(ticker) in _RECENT_SPINOFFS


def route_fair_value(
    ticker: str,
    *,
    ttm_eps: Optional[float] = None,
    ntm_eps: Optional[float] = None,
    ttm_pe: Optional[float] = None,
    quarters_of_clean_history: Optional[int] = None,  # for data-sanity gate
    total_quarters_history: Optional[int] = None,     # recent IPO gate (<8)
    is_acquisition_target: bool = False,
    sector: Optional[str] = None,  # e.g. "Real Estate", "Financial Services"
) -> FvRoute:
    """
    Route a ticker to the correct FV method / suppression decision.

    Parameters
    ----------
    ticker                   : Uppercase ticker symbol
    ttm_eps                  : Trailing-12m EPS (signed float, may be negative)
    ntm_eps                  : Next-12m (forward) EPS from analyst consensus
    ttm_pe                   : TTM Price/Earnings ratio (positive float or None)
    quarters_of_clean_history: Clean quarterly EPS records available. If < 4 for
                               a known spinoff ticker → suppress FV (data-sanity gate).
    total_quarters_history   : Total quarterly income rows available. If < 8 →
                               suppress FV (recent IPO / insufficient history).
    is_acquisition_target    : True → suppress FV and momentum signals entirely.
    sector                   : Optional sector string (from FMP/yfinance) for fallback
                               REIT / bank classification when ticker not in static sets.
    """
    t = normalize_ticker_key(ticker)
    notes: list[str] = []

    # ── §6a: Acquisition target — suppress everything ──────────────────────────
    if is_acquisition_target:
        return FvRoute(
            fv_suppressed=True,
            fv_suppressed_reason="ACQUISITION TARGET — deal pins price to terms",
            suppress_momentum=True,
            notes=["Price is pinned to deal terms — suppress FV and momentum signals."],
            gap_badge_type="METHOD",
        )

    # ── §5e: Commodity / metal ETFs — no PE-based FV ─────────────────────────
    if t in _COMMODITY_METAL_ETFS:
        return FvRoute(
            fv_suppressed=True,
            fv_suppressed_reason="COMMODITY ETF — technical anchor only (no earnings-based FV)",
            is_sector_override=True,
            method_label="technical anchor (commodity ETF — MA200 / band reference)",
            notes=[
                f"{t} has no earnings — PE/DCF fair value does not apply. "
                "Long-term anchor uses MA200 zone and macro context (real rates, DXY, flows). "
                "Street analyst targets are often empty for commodity ETFs — expected."
            ],
            gap_badge_type="METHOD",
        )

    # ── §6b: Crypto-correlated — earnings are a BTC derivative ────────────────
    if t in _CRYPTO_CORRELATED:
        return FvRoute(
            fv_suppressed=True,
            fv_suppressed_reason="CRYPTO-CORRELATED — earnings-based FV not applicable",
            notes=[
                f"{t} earnings track crypto prices directly. "
                "EV/holdings (for MSTR) or take-rate model (for COIN) is more appropriate. "
                "Use street consensus only."
            ],
            gap_badge_type="OPINION",
        )

    # ── §6: Recent IPO — insufficient quarterly history ─────────────────────
    if total_quarters_history is not None and total_quarters_history < 8:
        return FvRoute(
            fv_suppressed=True,
            fv_suppressed_reason="FV UNAVAILABLE — DATA (recent IPO / <8 quarters)",
            notes=[
                f"{t} has only {total_quarters_history} quarterly income records (<8). "
                "Model FV suppressed; house tiers may use street consensus only."
            ],
            gap_badge_type="METHOD",
        )

    # ── §6c: Recent spinoff / restatement — data-sanity gate ──────────────────
    if t in _RECENT_SPINOFFS:
        if quarters_of_clean_history is None:
            return FvRoute(
                fv_suppressed=True,
                fv_suppressed_reason="FV UNAVAILABLE — DATA (spinoff — EPS history unverified)",
                notes=[
                    f"{t} is a recent spinoff but quarterly EPS history could not be verified. "
                    "Model FV suppressed; show street consensus and tag house tiers accordingly."
                ],
                gap_badge_type="METHOD",
            )
        if quarters_of_clean_history < 4:
            return FvRoute(
                fv_suppressed=True,
                fv_suppressed_reason="FV UNAVAILABLE — DATA (recent spinoff / stub history)",
                notes=[
                    f"{t} has {quarters_of_clean_history} clean quarters (<4 post-corporate-action). "
                    "TTM EPS history is unreliable. Model FV suppressed; show street-only."
                ],
                gap_badge_type="METHOD",
            )
        notes.append(
            f"{t} is a recent spinoff ({quarters_of_clean_history} clean quarters). "
            "Verify split-adjusted price history before trusting Model FV."
        )

    # ── §5a: REITs — P/E destroys value via depreciation (most common retail FV error) ──
    is_reit = t in _REITS or (sector and "real estate" in str(sector).lower())
    if is_reit:
        return FvRoute(
            fv_suppressed=True,
            fv_suppressed_reason="REIT — P/FFO required (P/E meaningless due to depreciation)",
            is_sector_override=True,
            notes=[
                f"{t} is a REIT. P/E-based FV destroys value because depreciation "
                "suppresses GAAP EPS artificially. Use P/FFO or P/AFFO. "
                "Model FV suppressed; show street consensus and dividend yield instead."
            ],
            gap_badge_type="METHOD",
        )

    # ── §5b: Banks / financial holding companies ──────────────────────────────
    is_bank = t in _BANKS or (sector and "bank" in str(sector).lower())
    if is_bank:
        return FvRoute(
            fv_suppressed=True,
            fv_suppressed_reason="BANK — P/TBV vs ROTE is more appropriate than P/E vs sector",
            is_sector_override=True,
            notes=[
                f"{t} is a bank. P/E vs 'tech sector' P/E comps are meaningless. "
                "Correct metric: P/Tangible Book Value vs Return on Equity. "
                "Model FV suppressed; show street consensus."
            ],
            gap_badge_type="METHOD",
        )

    # ── §5b2: Asset managers — fee/AUM earnings, not product P/E growth ───────
    is_asset_manager = t in _ASSET_MANAGERS or (
        sector and "asset management" in str(sector).lower()
    )
    if is_asset_manager:
        return FvRoute(
            fv_suppressed=True,
            fv_suppressed_reason="ASSET MANAGER — P/E vs sector misstates fee-based earnings",
            is_sector_override=True,
            notes=[
                f"{t} is an asset / alt manager. Trailing P/E vs technology-sector comps "
                "overstates fair value when flows and fee rates drive EPS. "
                "Use street consensus (P/E on forward EPS × fee growth) or P/TBV vs ROE. "
                "Model FV suppressed; house tiers use analyst consensus."
            ],
            gap_badge_type="METHOD",
        )

    # ── §5c: Insurers ─────────────────────────────────────────────────────────
    if t in _INSURERS:
        return FvRoute(
            fv_suppressed=True,
            fv_suppressed_reason="INSURER — P/B vs ROE required",
            is_sector_override=True,
            notes=[
                f"{t} is an insurer. Use P/Book vs Return on Equity. "
                "PE-based methods produce misleading FV. BRK.B requires SOTP. "
                "Model FV suppressed."
            ],
            gap_badge_type="METHOD",
        )

    # ── §5d: MLPs / midstream ─────────────────────────────────────────────────
    if t in _MLPS:
        return FvRoute(
            fv_suppressed=True,
            fv_suppressed_reason="MLP/MIDSTREAM — EV/EBITDA + distribution coverage required",
            is_sector_override=True,
            notes=[
                f"{t} is an MLP/midstream operator. Use EV/EBITDA and distribution "
                "coverage ratios. PE-based FV is not applicable. Model FV suppressed."
            ],
            gap_badge_type="METHOD",
        )

    # ── §5e: Pre-revenue biotech ──────────────────────────────────────────────
    if t in _PREBIOTECH:
        return FvRoute(
            fv_suppressed=True,
            fv_suppressed_reason="PRE-REVENUE BIOTECH — pipeline / cash runway only",
            is_sector_override=True,
            notes=[
                f"{t} has no revenue-generating earnings base. "
                "FV depends on pipeline probability-weighted NPV and cash runway. "
                "Model FV suppressed; show street consensus with 'speculative' badge."
            ],
            gap_badge_type="METHOD",
        )

    # ── §6d: China ADRs — geopolitical discount is structural ─────────────────
    if t in _CHINA_ADRS:
        notes.append(
            f"{t} is a China ADR. The multiple compression vs peers is structural "
            "(geopolitical/regulatory risk premium), not a valuation opportunity. "
            "Cap any implied buy-signal bullishness. FV computed but treat with caution."
        )
        return FvRoute(
            fv_suppressed=False,
            geopolitical_cap=True,
            notes=notes,
            method_label="peg_blend (China ADR — geopolitical discount applies)",
            gap_badge_type="OPINION",
        )

    # ── §4a: Both EPS signs invalid — hard fallback ────────────────────────────
    ttm_eps_f = float(ttm_eps) if ttm_eps is not None else None
    ntm_eps_f = float(ntm_eps) if ntm_eps is not None else None
    both_available = ttm_eps_f is not None and ntm_eps_f is not None

    if ttm_eps_f is not None and ttm_eps_f <= 0 and ntm_eps_f is not None and ntm_eps_f <= 0:
        return FvRoute(
            fv_suppressed=True,
            fv_suppressed_reason="NEGATIVE EARNINGS — earnings-based methods invalid",
            notes=[
                f"{t} has TTM EPS {ttm_eps_f:.2f} and NTM EPS {ntm_eps_f:.2f} — "
                "both non-positive. Use EV/S, analyst NTM EPS, or show street-only."
            ],
            gap_badge_type="METHOD",
        )

    if ttm_eps_f is not None and ttm_eps_f <= 0:
        # Negative TTM but positive NTM → allow forward-only; ticker_detail already handles this
        notes.append(
            f"{t} TTM EPS is non-positive ({ttm_eps_f:.2f}). "
            "Using analyst forward EPS only — PE-relative anchor bypassed."
        )
        return FvRoute(
            fv_suppressed=False,
            force_forward_pe=True,
            notes=notes,
            method_label="analyst_forward_eps (TTM negative)",
            gap_badge_type="METHOD",
        )

    # ── §4b: Near-zero EPS crossover — P/E is noise (P/E > 200×) ─────────────
    if ttm_eps_f is not None and 0 < ttm_eps_f < _NEAR_ZERO_EPS_THRESHOLD:
        if ttm_pe is not None and ttm_pe > 200:
            notes.append(
                f"{t} TTM EPS is near-zero ({ttm_eps_f:.2f}) → P/E {ttm_pe:.0f}× is meaningless. "
                "Route to EV/S or forward-EPS method."
            )
            return FvRoute(
                fv_suppressed=False,
                force_forward_pe=True,
                notes=notes,
                method_label="forward_pe (near-zero TTM EPS crossover)",
                gap_badge_type="METHOD",
            )

    # ── §0: Divergence trigger — catches MU/NVDA/LLY class dynamically ────────
    divergence = _calc_divergence(ttm_eps_f, ntm_eps_f) if both_available else None
    if divergence is not None and divergence > _DIVERGENCE_TRIGGER_PCT:
        direction = "up" if (ntm_eps_f or 0) > (ttm_eps_f or 0) else "down"
        notes.append(
            f"NTM/TTM EPS divergence {divergence:.0f}% (>{_DIVERGENCE_TRIGGER_PCT:.0f}% trigger). "
            f"Earnings trend sharply {direction} — switching to forward P/E method."
        )
        # §1: Deep cyclicals always force forward (but some may already be in the static set above)
        is_dc = t in _DEEP_CYCLICALS
        label = (
            f"forward_pe (cyclical — TTM/NTM divergence {divergence:.0f}%)"
            if is_dc else
            f"forward_pe (TTM/NTM divergence {divergence:.0f}%)"
        )
        return FvRoute(
            fv_suppressed=False,
            force_forward_pe=True,
            is_deep_cyclical=is_dc,
            divergence_pct=round(divergence, 1),
            notes=notes,
            method_label=label,
            gap_badge_type="METHOD",
        )

    # ── §1: Deep cyclical static override (even without EPS data available) ───
    if t in _DEEP_CYCLICALS:
        notes.append(
            f"{t} is a deep cyclical. TTM P/E inverts the signal at cycle extremes "
            "(cheap at high P/E, expensive at low P/E). Using forward P/E anchored to NTM EPS."
        )
        return FvRoute(
            fv_suppressed=False,
            force_forward_pe=True,
            is_deep_cyclical=True,
            divergence_pct=round(divergence, 1) if divergence is not None else None,
            notes=notes,
            method_label="forward_pe (deep cyclical — TTM P/E unreliable)",
            gap_badge_type="METHOD",
        )

    # ── §3: Steady compounders — default peg_blend is fine ───────────────────
    # Add divergence info even when below threshold (transparency)
    if divergence is not None:
        notes.append(
            f"NTM/TTM EPS divergence {divergence:.0f}% (below {_DIVERGENCE_TRIGGER_PCT:.0f}% trigger) "
            "— peg_blend on TTM P/E is appropriate."
        )

    return FvRoute(
        fv_suppressed=False,
        force_forward_pe=False,
        divergence_pct=round(divergence, 1) if divergence is not None else None,
        notes=notes,
        method_label="peg_blend",
        gap_badge_type="METHOD",
    )


# ══════════════════════════════════════════════════════════════════════════════
# §8 UI helpers — method label and gap-badge classification
# ══════════════════════════════════════════════════════════════════════════════

# Tickers where a large model-vs-street gap is likely genuine opinion divergence
# (narrative premium) rather than a method error — badge as GAP:OPINION.
_NARRATIVE_PREMIUM_TICKERS: frozenset[str] = frozenset({
    "TSLA",     # part hypergrowth, part cyclical, part story stock
    "PLTR",     # high structural PE; model PEG vs street's TAM narrative
    "MSTR",     # bitcoin treasury play; any EPS FV vs street is opinion
    "HOOD",     # payment-for-orderflow regime risk; high opinion divergence
    "SMCI",     # audit/governance risk creates wide street dispersion
})


def classify_gap_badge(
    ticker: str,
    model_fv: float,
    street_price: Optional[float],
    route: Optional[FvRoute] = None,
) -> str:
    """
    Return 'METHOD' (fixable routing error) or 'OPINION' (genuine disagreement = alpha).

    §8 rule:
      - If route surfaced a suppression or forward-pe override → likely METHOD
      - If ticker is in narrative-premium list → OPINION (model genuinely disagrees with street)
      - Otherwise default METHOD so users don't assume the model is always right
    """
    t = str(ticker).upper()
    if t in _NARRATIVE_PREMIUM_TICKERS:
        return "OPINION"
    if route and route.gap_badge_type == "OPINION":
        return "OPINION"
    # China ADRs: structural discount → OPINION (model can't price geopolitical risk)
    if t in _CHINA_ADRS:
        return "OPINION"
    return "METHOD"
