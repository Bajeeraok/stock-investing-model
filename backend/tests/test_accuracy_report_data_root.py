import json

from scripts.accuracy_price_targets import run_accuracy_and_save


def test_accuracy_report_written_to_data_root(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    path = run_accuracy_and_save([], {})
    assert path == tmp_path / "accuracy_price_targets.json"
    assert "as_of" in json.loads(path.read_text())
