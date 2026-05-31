"""HuggingFace text-classification pipeline wrapper."""
import logging
from typing import Optional
from transformers import Pipeline, pipeline

import config

logger = logging.getLogger(__name__)


class _Scanner:
    """Wraps the HuggingFace text-classification pipeline."""

    def __init__(self):
        """
        Initialize the scanner instance without a loaded Hugging Face pipeline.
        
        Sets self._pipe to None; the pipeline is created when load() is called.
        """
        self._pipe: Optional[Pipeline] = None

    def load(self):
        """
        Initialize and load the Hugging Face text-classification pipeline using config.MODEL and validate that config.INJECTION_LABEL is present in the model's labels.
        
        Raises:
            RuntimeError: If config.INJECTION_LABEL is not among the model's labels.
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
        Determine whether the provided text is injection-safe according to the loaded model.
        
        Parameters:
            text (str): Input text to evaluate for injection risk.
        
        Returns:
            tuple[bool, float]: A pair (is_safe, injection_score). `is_safe` is `True` if the model's
            score for `config.INJECTION_LABEL` is less than `config.THRESHOLD`, `False` otherwise.
            `injection_score` is the model's score for `config.INJECTION_LABEL`, rounded to four decimal places.
        
        Raises:
            RuntimeError: If the scanner has not been loaded via `load()`.
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
    """
    Initialize and load the module's text-classification pipeline.
    
    Delegates to the module-level scanner to create and validate the Hugging Face pipeline configured by `config.MODEL` and `config.INJECTION_LABEL`.
    """
    _SCANNER.load()


def scan(text: str) -> tuple[bool, float]:
    """
    Assess whether the provided text is safe from prompt injection.
    
    Parameters:
        text (str): Text to evaluate for injection risk.
    
    Returns:
        (is_safe, injection_score) (tuple[bool, float]): `is_safe` is `True` if the model's injection score is less than the configured threshold, `False` otherwise. `injection_score` is the model's score for the configured injection label, rounded to four decimal places.
    """
    return _SCANNER.scan(text)
