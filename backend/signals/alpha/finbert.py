"""
Optional FinBERT headline sentiment (ProsusAI/finbert).

Off unless ``FINBERT_ENABLED=1`` and ``transformers`` + ``torch`` are installed (they are
not in requirements.txt — ~1 GB). Returns None when unavailable so callers keep the
keyword lexicon score.
"""
from __future__ import annotations

import logging
import os
import threading
from functools import lru_cache

logger = logging.getLogger(__name__)
MODEL_NAME = os.environ.get("FINBERT_MODEL", "ProsusAI/finbert")
_LOCK = threading.Lock()


def finbert_enabled() -> bool:
    return (os.environ.get("FINBERT_ENABLED") or "").strip().lower() in ("1", "true", "yes", "on")


@lru_cache(maxsize=1)
def _pipeline():
    try:
        from transformers import pipeline

        return pipeline("text-classification", model=MODEL_NAME, top_k=None, truncation=True)
    except Exception as e:  # missing deps / no network
        logger.warning("FinBERT unavailable: %s", e)
        return None


def label_scores_to_signed(scores: list[dict]) -> float:
    """[{'label': 'positive', 'score': p}, ...] -> P(positive) - P(negative) in [-1, 1]."""
    d = {str(s["label"]).lower(): float(s["score"]) for s in scores}
    return d.get("positive", 0.0) - d.get("negative", 0.0)


def finbert_score(text: str) -> float | None:
    if not finbert_enabled() or not (text or "").strip():
        return None
    with _LOCK:
        pipe = _pipeline()
        if pipe is None:
            return None
        try:
            out = pipe(text[:512])
        except Exception as e:
            logger.debug("FinBERT inference failed: %s", e)
            return None
    rows = out[0] if out and isinstance(out[0], list) else out
    return label_scores_to_signed(rows)
