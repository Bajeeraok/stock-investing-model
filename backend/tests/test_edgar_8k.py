from datetime import date

from signals.edgar_8k import events_from_submissions
from signals.investor_rules import evaluate_rules

SUB = {
    "cik": "0001045810",
    "filings": {"recent": {
        "form": ["8-K", "4", "8-K", "8-K"],
        "filingDate": ["2026-11-12", "2026-11-11", "2026-11-10", "2026-09-01"],
        "items": ["5.02,9.01", "", "2.02,9.01", "4.02"],
        "accessionNumber": ["a1", "a2", "a3", "a4"],
    }},
}


def test_parse_and_story_items():
    ev = events_from_submissions(SUB, date(2026, 11, 5))
    assert [e["accession"] for e in ev] == ["a1", "a3"]  # Form 4 and old filing dropped
    assert ev[0]["story"] == ["5.02"] and ev[0]["labels"] == ["Director or officer change"]
    assert ev[1]["story"] == [] and not ev[1]["severe"]


def test_rule_hit_only_for_story_items():
    ev = events_from_submissions(SUB, date(2026, 11, 5))
    rows = [{"ticker": "NVDA", "sec_8k": ev}, {"ticker": "AAPL", "sec_8k": [ev[1]]}]
    out = evaluate_rules(rows, {}, today="2026-11-12")
    rule = next(r for r in out["rules"] if r["id"] == "sec_8k_story")
    hits = {h["ticker"]: h["detail"] for h in rule["hits"]}
    assert set(hits) == {"NVDA"} and "Director or officer change" in hits["NVDA"]


def test_severe_flag():
    ev = events_from_submissions(SUB, date(2026, 8, 1))
    rows = [{"ticker": "X", "sec_8k": [ev[-1]]}]
    rule = next(r for r in evaluate_rules(rows, {}, today="2026-11-12")["rules"] if r["id"] == "sec_8k_story")
    assert rule["hits"][0]["detail"].startswith("SEVERE")
