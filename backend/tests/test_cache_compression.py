"""Large Redis values are zlib-compressed; small/legacy values read unchanged."""
from signals.cache import _COMPRESS_PREFIX, _deserialize, _serialize


def test_large_value_round_trips_compressed():
    big = {"rows": [{"ticker": f"T{i}", "close": i * 1.5, "note": "x" * 50} for i in range(2000)]}
    raw = _serialize(big)
    assert raw.startswith(_COMPRESS_PREFIX)
    assert len(raw) < len(str(big)) / 3
    assert _deserialize(raw) == big


def test_small_and_legacy_values_unchanged():
    small = {"a": 1}
    raw = _serialize(small)
    assert not raw.startswith(_COMPRESS_PREFIX)
    assert _deserialize(raw) == small
    assert _deserialize('{"legacy": true}') == {"legacy": True}
    assert _deserialize("plain-string", as_json=False) == "plain-string"
