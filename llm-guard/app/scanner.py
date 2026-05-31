"""HuggingFace text-classification pipeline wrapper."""
import logging
from typing import Optional
from transformers import Pipeline, pipeline

import config

logger = logging.getLogger(__name__)


class _Scanner:
    """Wraps the HuggingFace text-classification pipeline."""

    def __init__(self):
        """Initialize with no pipeline loaded."""
        self._pipe: Optional[Pipeline] = None

    def load(self):
        """
        Load the HuggingFace pipeline and validate INJECTION_LABEL.

        Raises:
            RuntimeError: If config.INJECTION_LABEL is not in the model's labels.
        """
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
        """
        Evaluate text for prompt injection.

        Returns:
            tuple[bool, float]: (is_safe, injection_score) where injection_score
            is the model's score for config.INJECTION_LABEL rounded to 4 dp.

        Raises:
            RuntimeError: If load() has not been called.
        """
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
    """Load the module-level scanner pipeline."""
    _SCANNER.load()


def scan(text: str) -> tuple[bool, float]:
    """Assess whether text is safe from prompt injection."""
    return _SCANNER.scan(text)
