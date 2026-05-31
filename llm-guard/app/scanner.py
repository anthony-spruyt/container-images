import logging
from transformers import pipeline

import config

logger = logging.getLogger(__name__)

_pipe = None


def load():
    global _pipe
    logger.info("loading model", extra={"model": config.MODEL})
    _pipe = pipeline(
        "text-classification",
        model=config.MODEL,
        device=-1,
        truncation=True,
        max_length=512,
    )
    logger.info("model ready")


def scan(text: str) -> tuple[bool, float]:
    """Return (is_safe, injection_score)."""
    result = _pipe(text)[0]
    label: str = result["label"]
    raw_score: float = result["score"]

    injection_score = raw_score if label == config.INJECTION_LABEL else 1.0 - raw_score
    is_safe = injection_score < config.THRESHOLD

    logger.info(
        "scan result",
        extra={
            "label": label,
            "raw_score": raw_score,
            "injection_score": injection_score,
            "is_safe": is_safe,
        },
    )
    return is_safe, round(injection_score, 4)
