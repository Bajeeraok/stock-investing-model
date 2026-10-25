from signals.alpha import finbert


def test_disabled_returns_none(monkeypatch):
    monkeypatch.delenv("FINBERT_ENABLED", raising=False)
    assert finbert.finbert_score("Apple beats estimates") is None


def test_signed_score_and_stubbed_pipeline(monkeypatch):
    assert finbert.label_scores_to_signed(
        [{"label": "positive", "score": 0.7}, {"label": "negative", "score": 0.2}, {"label": "neutral", "score": 0.1}]
    ) == 0.7 - 0.2
    monkeypatch.setenv("FINBERT_ENABLED", "1")
    monkeypatch.setattr(finbert, "_pipeline", lambda: (lambda t: [[{"label": "negative", "score": 0.9}]]))
    assert finbert.finbert_score("Guidance cut") == -0.9
