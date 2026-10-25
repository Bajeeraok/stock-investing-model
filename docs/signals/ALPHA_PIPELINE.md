# Benchmark-relative alpha pipeline (`backend/signals/alpha/`)

Goal: only act on a stock when similar setups have **beaten SPY after costs**; otherwise say "Prefer SPY".

| Piece | Module | Script / API |
|---|---|---|
| Excess vs SPY on every outcome, cohort expectancy, Prefer-SPY verdict | `alpha/excess.py`, `forward_tracking.py`, `retail_action_payload.py` | `scripts/build_cohort_expectancy.py`, `GET /api/alpha/cohorts` |
| Purged train / val / test split for per-ticker LightGBM | `ml_models.purged_split_bounds` | — |
| Labels: beat-SPY-after-cost, triple-barrier (target before stop) | `alpha/labels.py` | — |
| Relative features (vs SPY, vs sector ETF, cross-sectional ranks) | `alpha/features.py` | — |
| Survivorship-aware S&P 500 membership (incl. removed names) | `alpha/universe.py` | `scripts/build_universe.py` → `data/universe/sp500_membership.csv` |
| Pooled model, purged walk-forward, locked 12-month holdout, isotonic calibration, return quantiles, promotion gates | `alpha/pooled_model.py` | `scripts/train_alpha_model.py`, `GET /api/alpha/model` |
| Learned layer weights (used only if they beat hand-set weights out of sample) | `alpha/stacker.py`, `confidence_engine.py` | `scripts/fit_layer_weights.py` |
| Measured win-rate / payoff for Kelly sizing | `excess.measured_kelly_inputs`, `tier1_risk_engine.size_position_for_ticker` | — |
| Rank-and-pick portfolio (sector cap, correlation cap, inverse-vol, vol target) | `alpha/portfolio.py` | `scripts/alpha_daily.py`, `GET /api/alpha/picks` |
| Point-in-time feature store | `alpha/pit_store.py` | written by `alpha_daily.py` |
| Drift monitoring (feature PSI, calibration ECE, edge decay) | `alpha/drift.py` | `GET /api/alpha/drift` |
| Alpaca **paper** trading (paper endpoint pinned) | `brokers/alpaca_paper.py` | `scripts/alpaca_paper_sync.py` (dry run unless `--submit`) |
| Optional FinBERT headline sentiment | `alpha/finbert.py` | `FINBERT_ENABLED=1` + `pip install transformers torch` |

## Run order

```bash
cd backend
python scripts/build_universe.py
python scripts/train_alpha_model.py --max-tickers 200 --years 12   # writes data/alpha/pooled_model.{pkl,json}
python scripts/alpha_daily.py                                      # picks, PIT store, drift report
python scripts/build_cohort_expectancy.py                          # needs EOD snapshot history
export ALPACA_API_KEY=... ALPACA_SECRET_KEY=...                    # optional
python scripts/alpaca_paper_sync.py                                # dry run; add --submit for paper orders
```

With no artifacts present nothing changes in the live app: Prefer-SPY needs ≥ `alpha.prefer_index.min_n`
tracked outcomes per cohort, learned weights must beat the defaults out of sample, and `alpha_daily.py`
only uses horizons whose walk-forward **and** holdout metrics pass the promotion gates.

## Known limits
- Free price data lacks many delisted tickers, so some survivorship bias remains even with PIT membership.
- Layer-weight learning needs per-layer scores persisted on outcome rows (`layer_scores`).
