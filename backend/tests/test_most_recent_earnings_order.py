from unittest.mock import patch

import pandas as pd

from signals import providers


def test_most_recent_earnings_picks_newest_past_date():
    now = pd.Timestamp.now().normalize()
    idx = pd.DatetimeIndex([now + pd.Timedelta(days=80), now - pd.Timedelta(days=10), now - pd.Timedelta(days=100),
                            now - pd.Timedelta(days=2000)])
    fake = type("T", (), {"earnings_dates": pd.DataFrame({"EPS Estimate": [1, 1, 1, 1]}, index=idx)})()
    with patch.object(providers.yf, "Ticker", return_value=fake):
        out = providers._get_most_recent_earnings_impl("ZZZZ", {})
    assert out["days_since"] == 10
