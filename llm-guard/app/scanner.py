"""HuggingFace text-classification pipeline wrapper."""
import logging
from typing import Optional
from transformers import Pipeline, pipeline

import config

logger = logging.getLogger(__name__)


class _Scanner:
    """Wraps the HuggingFace text-classification pipeline."""

    def __init__(self):
        self._pipe: Optional[Pipeline] = None

    def load(self):
        """Load the model into the pipeline."""
        logger.info("loading model", extra={"model": config.MODEL})
        self._pipe = pipeline(
            "text-classification",
            model=config.MODEL,
            device=-1,
            truncation=True,
            max_length=512,
            top_k=None,
        )
        known_labels = set(self._pipe.model.config.label2id.keys())
        if config.INJECTION_LABEL not in known_labels:
            raise RuntimeError(
                f"INJECTION_LABEL {config.INJECTION_LABEL!r} not in model labels: {known_labels}"
            )
        logger.info("model ready")

    def scan(self, text: str) -> tuple[bool, float]:
        """Return (is_safe, injection_score) for the given text."""
        if self._pipe is None:
            raise RuntimeError("Scanner not loaded; call load() first")
        results = self._pipe(text)
        flat = results[0] if results and isinstance(results[0], list) else results
        scores = {r["label"]: r["score"] for r in flat}
        injection_score = scores.get(config.INJECTION_LABEL, 0.0)
        is_safe = injection_score < config.THRESHOLD
        logger.info(
            "scan result",
            extra={"injection_score": injection_score, "is_safe": is_safe},
        )
        return is_safe, round(injection_score, 4)


_SCANNER = _Scanner()


def load():
    """Load the model at startup."""
    _SCANNER.load()


def scan(text: str) -> tuple[bool, float]:
    """Return (is_safe, injection_score) for the given text."""
    return _SCANNER.scan(text)
