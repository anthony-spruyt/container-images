"""Individual scanner implementations."""
import logging
import re
import unicodedata
from dataclasses import dataclass
from typing import Optional
from transformers import Pipeline, pipeline

import config

logger = logging.getLogger(__name__)

# Cf = Unicode format chars (zero-width, directional overrides, etc.)
# Cc (control chars) intentionally excluded — it includes \n \r \t
_INVISIBLE_CATEGORIES = frozenset({"Cf"})
_INVISIBLE_CODEPOINTS = frozenset({
    0x00AD,  # soft hyphen
    0x200B,  # zero-width space
    0x200C,  # zero-width non-joiner
    0x200D,  # zero-width joiner
    0x2060,  # word joiner
    0xFEFF,  # zero-width no-break space / BOM
})


@dataclass
class ScanResult:
    """Result from a single scanner."""

    scanner: str
    is_safe: bool
    score: float
    reason: Optional[str] = None


class PromptInjectionScanner:
    """Detects prompt injection using a HuggingFace text-classification model."""

    def __init__(self, **kwargs):
        """
        Initialise the scanner from keyword arguments.

        Kwargs:
            model (str): HuggingFace model ID. Defaults to config.DEFAULT_MODEL.
            injection_label (str): Positive-class label. Defaults to config.DEFAULT_INJECTION_LABEL.
            threshold (float): Block threshold [0,1]. Defaults to config.DEFAULT_THRESHOLD.
            match_type (str): ``"full"`` or ``"sentence"``. Defaults to ``"full"``.
            model_max_length (int): Max token length. Defaults to 512.
        """
        self._model = kwargs.get("model", "") or config.DEFAULT_MODEL
        self._injection_label = kwargs.get("injection_label", "") or config.DEFAULT_INJECTION_LABEL
        threshold = kwargs.get("threshold", None)
        self._threshold = config.DEFAULT_THRESHOLD if threshold is None else threshold
        self._match_type = kwargs.get("match_type", "full")
        self._model_max_length = kwargs.get("model_max_length", 512)
        self._pipe: Optional[Pipeline] = None
        self._injection_label_missing_warned = False

    def load(self):
        """Load the HuggingFace pipeline and validate the injection label exists."""
        logger.info("loading model", extra={"model": self._model})
        self._pipe = pipeline(
            "text-classification",
            model=self._model,
            device=-1,
            truncation=True,
            max_length=self._model_max_length,
            top_k=None,
        )
        known_labels = self._known_labels()
        if known_labels and self._injection_label not in known_labels:
            raise RuntimeError(
                f"injection_label {self._injection_label!r} not in model labels: {known_labels}"
            )
        if not known_labels:
            # Some models populate only one of label2id/id2label, or neither
            # (e.g. generic LABEL_0/LABEL_1). Can't validate up front; the
            # label is resolved per-inference from pipeline output instead.
            logger.warning(
                "model exposes no label map; skipping injection_label validation",
                extra={"injection_label": self._injection_label},
            )
        logger.info("model ready")

    def _known_labels(self) -> set:
        """Return the model's label names from label2id or id2label, if any."""
        cfg = self._pipe.model.config
        label2id = getattr(cfg, "label2id", None)
        if label2id:
            return set(label2id.keys())
        id2label = getattr(cfg, "id2label", None)
        if id2label:
            return set(id2label.values())
        return set()

    def _score_text(self, text: str) -> float:
        """Return injection score [0,1] for a single text chunk."""
        if self._pipe is None:
            raise RuntimeError("PromptInjectionScanner not loaded; call load() first")
        results = self._pipe(text)
        flat = results[0] if results and isinstance(results[0], list) else results
        scores = {r["label"]: r["score"] for r in flat}
        if self._injection_label not in scores and not self._injection_label_missing_warned:
            # Fail-open: a missing label means every prompt scores 0.0. Warn
            # once so the silent pass-through is observable at runtime.
            logger.warning(
                "injection_label not in model output; scanner fails open (scores 0.0)",
                extra={"injection_label": self._injection_label,
                       "model_labels": sorted(scores.keys())},
            )
            self._injection_label_missing_warned = True
        return scores.get(self._injection_label, 0.0)

    @staticmethod
    def _split_sentences(text: str) -> list:
        """Split text into sentences on .  !  ? boundaries."""
        parts = re.split(r"(?<=[.!?])\s+", text.strip())
        return [p for p in parts if p]

    def scan(self, text: str) -> ScanResult:
        """
        Scan text for prompt injection.

        Returns:
            ScanResult with is_safe=True if injection score is below threshold.
        """
        if self._match_type == "sentence":
            sentences = self._split_sentences(text) or [text]
            injection_score = max(self._score_text(s) for s in sentences)
        else:
            injection_score = self._score_text(text)

        is_safe = injection_score < self._threshold
        return ScanResult(
            scanner="PromptInjection",
            is_safe=is_safe,
            score=round(injection_score, 4),
            reason=None if is_safe else (
                f"injection score {injection_score:.4f} >= {self._threshold}"
            ),
        )


class RegexScanner:
    """Blocks text matching configurable regex patterns (e.g. credential leakage)."""

    def __init__(
        self,
        patterns: Optional[list] = None,
        is_blocked: bool = True,
        match_type: str = "search",
        redact: bool = False,
    ):
        """
        Initialise the scanner.

        Args:
            patterns: List of regex pattern strings to match.
            is_blocked: If True, a match means the text is unsafe.
            match_type: ``"search"`` (anywhere in text) or ``"fullmatch"`` (whole string).
            redact: Unused; kept for config compatibility.
        """
        self._compiled = [re.compile(p) for p in (patterns or [])]
        self._is_blocked = is_blocked
        self._match_type = match_type
        self._redact = redact

    def load(self):
        """No-op; patterns are compiled at init."""

    def scan(self, text: str) -> ScanResult:
        """
        Scan text against configured regex patterns.

        Returns:
            ScanResult with is_safe=False if a blocking pattern matches.
        """
        for pat in self._compiled:
            if self._match_type == "search":
                matched = pat.search(text) is not None
            elif self._match_type == "fullmatch":
                matched = pat.fullmatch(text) is not None
            else:
                raise ValueError(f"Unknown match_type: {self._match_type!r}")
            if self._is_blocked:
                if matched:
                    return ScanResult(
                        scanner="Regex",
                        is_safe=False,
                        score=1.0,
                        reason=f"matched blocked pattern: {pat.pattern!r}",
                    )
            else:
                if not matched:
                    return ScanResult(
                        scanner="Regex",
                        is_safe=False,
                        score=1.0,
                        reason=f"did not match required pattern: {pat.pattern!r}",
                    )
        return ScanResult(scanner="Regex", is_safe=True, score=0.0)


class InvisibleTextScanner:
    """Detects invisible/zero-width Unicode characters used in injection attacks."""

    def load(self):
        """No-op; no resources to load."""

    def scan(self, text: str) -> ScanResult:
        """
        Scan text for invisible Unicode characters.

        Returns:
            ScanResult with is_safe=False if invisible characters are found.
        """
        found = [
            ch for ch in text
            if ord(ch) in _INVISIBLE_CODEPOINTS
            or unicodedata.category(ch) in _INVISIBLE_CATEGORIES
        ]
        if found:
            codepoints = ", ".join(f"U+{ord(c):04X}" for c in set(found))
            return ScanResult(
                scanner="InvisibleText",
                is_safe=False,
                score=1.0,
                reason=f"invisible characters detected: {codepoints}",
            )
        return ScanResult(scanner="InvisibleText", is_safe=True, score=0.0)
