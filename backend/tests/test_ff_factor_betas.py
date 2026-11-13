import numpy as np
import pandas as pd

from portfolio.ff_factor_betas import FACTORS, compute_ff_betas, parse_french_csv

CSV = """This file was created by CRSP.

,Mkt-RF,SMB,HML,RMW,CMA,RF
20260929,   -0.26,    0.10,   -0.88,   -0.35,    0.19,    0.01
20260930,    0.50,   -99.99,   0.10,    0.05,   -0.20,    0.01

Copyright 2026 Eugene F. Fama and Kenneth R. French
"""


def test_parse():
    df = parse_french_csv(CSV)
    assert list(df.columns) == ["Mkt-RF", "SMB", "HML", "RMW", "CMA", "RF"]
    assert abs(df.iloc[0]["HML"] + 0.0088) < 1e-9 and np.isnan(df.iloc[1]["SMB"])


def test_recovers_known_betas():
    rng = np.random.default_rng(0)
    idx = pd.bdate_range("2025-06-01", periods=300)
    f = pd.DataFrame(rng.normal(0, 0.01, (300, 6)), index=idx, columns=FACTORS)
    f["RF"] = 0.0001
    true = {"Mkt-RF": 1.4, "SMB": 0.0, "HML": -0.5, "RMW": 0.0, "CMA": 0.0, "Mom": 0.6}
    r = f["RF"] + sum(f[k] * v for k, v in true.items()) + rng.normal(0, 0.002, 300)
    prices = pd.DataFrame({"AIX": 100 * (1 + r).cumprod()})
    out = compute_ff_betas([{"ticker": "AIX", "pct": 100}], factors=f, prices=prices)
    b = out["book_betas"]
    assert abs(b["Mkt-RF"] - 1.4) < 0.1 and abs(b["Mom"] - 0.6) < 0.1 and abs(b["HML"] + 0.5) < 0.1
    assert out["r2"] > 0.9 and len(out["flags"]) == 3
