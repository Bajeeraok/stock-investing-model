import json

from signals import best_setups


def test_save_report_keeps_dated_rows_with_rank(tmp_path, monkeypatch):
    monkeypatch.setattr(best_setups, "_dir", lambda: tmp_path)
    rows = {"swing": [{"ticker": "AAA", "edge_pct": 2.0, "chance": 50, "qualified": True, "blockers": []},
                      {"ticker": "BBB", "edge_pct": 5.0, "chance": 50, "qualified": False, "blockers": ["entry gates"]}]}
    best_setups.rank(rows)
    assert {r["ticker"]: r["rank"] for r in rows["swing"]} == {"BBB": 1, "AAA": 2}
    report = {"as_of": "2026-11-16", "modes": {},
              "_rows": {m: {r["ticker"]: {k: r.get(k) for k in best_setups._ROW_KEYS} for r in rs} for m, rs in rows.items()}}
    best_setups.save_report(report)
    assert best_setups.row_days() == ["2026-11-16"]
    saved = best_setups.load_rows_for("2026-11-16")
    assert saved["modes"]["swing"]["BBB"]["rank"] == 1 and saved["modes"]["swing"]["AAA"]["edge_pct"] == 2.0
    assert best_setups.load_rows_for("2026-11-15") is None
    assert json.loads((tmp_path / "rows.json").read_text()) == saved
