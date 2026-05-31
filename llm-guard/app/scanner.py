"""HuggingFace text-classification pipeline wrapper."""
import logging
from transformers import pipeline

import config

logger = logging.getLogger(__name__)

_PIPE = [None]  # mutable container — avoids module-level global statement


def load():
    """Load the model into the pipeline at startup."""
    logger.info("loading model", extra={"model": config.MODEL})
    _PIPE[0] = pipeline(
        "text-classification",
        model=config.MODEL,
        device=-1,
        truncation=True,
        max_length=512,
        top_k=None,
    )
    logger.info("model ready")


def scan(text: str) -> tuple[bool, float]:
    """Return (is_safe, injection_score) for the given text."""
    results = _PIPE[0](text)
    scores = {r["label"]: r["score"] for r in results}
    injection_score = scores.get(config.INJECTION_LABEL, 0.0)
    is_safe = injection_score < config.THRESHOLD

    logger.info(
        "scan result",
        extra={"injection_score": injection_score, "is_safe": is_safe},
    )
    return is_safe, round(injection_score, 4)
