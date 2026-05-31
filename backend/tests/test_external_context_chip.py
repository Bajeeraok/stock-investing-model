from signals.external_context_chip import build_external_context_chip


def test_msft_like_overbought_bullish_mas():
    chip = build_external_context_chip(
        rsi=70,
        current_price=450.24,
        ma20=440,
        ma50=420,
        ma200=400,
        macd_hist=1.2,
        regime="UP",
    )
    assert chip["rsi_zone"] == "overbought"
    assert chip["ma_alignment"] == "bullish"
    assert chip["screener_alignment"] == "mixed"
    assert "overbought" in chip["summary_line"].lower() or "Strong Buy" in chip["summary_line"]


def test_oversold_bullish_dip():
    chip = build_external_context_chip(rsi=32, current_price=100, ma20=95, ma50=90, ma200=85)
    assert chip["screener_alignment"] == "agree_dip"
