"""DATA_ROOT vs packaged backend/data cache lookup."""
from __future__ import annotations

from pathlib import Path

from config_loader import (
    bundled_data_root,
    resolve_existing_data_file,
    writable_data_path,
)


def test_resolve_prefers_data_root_then_bundled(tmp_path, monkeypatch):
    bundled = bundled_data_root()
    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    rel = ("edgar_13f_cache", "holder_cik_map.json")
    bundled_file = bundled.joinpath(*rel)
    volume_file = tmp_path.joinpath(*rel)
    volume_file.parent.mkdir(parents=True, exist_ok=True)
    volume_file.write_text('{"from":"volume"}', encoding="utf-8")
    found = resolve_existing_data_file(*rel)
    assert found is not None
    assert found.resolve() == volume_file.resolve()
    volume_file.unlink()
    if bundled_file.is_file():
        found = resolve_existing_data_file(*rel)
        assert found is not None
        assert found.resolve() == bundled_file.resolve()


def test_writable_data_path_under_data_root(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    path = writable_data_path("edgar_13f_cache", "snapshot_NVDA.json")
    assert path.parent.resolve() == (Path(tmp_path) / "edgar_13f_cache").resolve()
    assert path.name == "snapshot_NVDA.json"
