"""Tests for behavior.trade_discipline — trim cooldown + journal."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from behavior import trade_discipline as td


@pytest.fixture
def discipline_file(tmp_path, monkeypatch):
    p = tmp_path / "trade_discipline.json"
    monkeypatch.setattr(td, "_path", lambda: p)
    return p


def test_add_allowed_when_no_cooldown(discipline_file):
    config = {"behavior": {"cooldown_days_after_trim": 14}}
    out = td.check_add_allowed("AAPL", config)
    assert out["allowed"] is True


def test_trim_cooldown_blocks_readd(discipline_file):
    config = {"behavior": {"cooldown_days_after_trim": 7}}
    rec = td.record_trim_cooldown("MSFT", config, note="Taking profits")
    assert rec["ok"] is True
    assert rec["cooldown_days"] == 7

    blocked = td.check_add_allowed("MSFT", config)
    assert blocked["allowed"] is False
    assert blocked["days_left"] >= 6
    assert blocked["reason"] == "trim"


def test_thesis_override_skips_cooldown(discipline_file):
    config = {"behavior": {"cooldown_days_after_trim": 14}}
    td.record_trim_cooldown("NVDA", config)
    out = td.check_add_allowed("NVDA", config, thesis_override=True)
    assert out["allowed"] is True


def test_journal_append_and_list(discipline_file):
    config = {"behavior": {"journal_max_entries": 5}}
    td.append_journal("AAPL", "add", "Pullback to MA50", config)
    td.append_journal("TSLA", "trim", "Score dropped", config)
    td.append_journal("NVDA", "note", "NVDA · earnings beat (unlocks) — print held. Advisory only.", config)
    entries = td.list_journal(10)
    assert len(entries) == 3
    assert entries[0]["ticker"] == "NVDA"
    assert entries[0]["action"] == "note"
    assert entries[1]["ticker"] == "TSLA"
    assert entries[1]["action"] == "trim"


def test_expired_cooldown_allows_add(discipline_file):
    config = {"behavior": {"cooldown_days_after_trim": 1}}
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    import json

    with open(discipline_file, "w", encoding="utf-8") as f:
        json.dump({"cooldowns": {"META": {"until": yesterday, "reason": "trim"}}, "journal": []}, f)

    out = td.check_add_allowed("META", config)
    assert out["allowed"] is True
