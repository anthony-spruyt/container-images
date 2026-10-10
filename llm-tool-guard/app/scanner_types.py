"""Individual scanner implementations."""

import logging
import re
import unicodedata
from dataclasses import dataclass

import torch
from transformers import Pipeline, pipeline

import config

logger = logging.getLogger(__name__)

# Cf = Unicode format chars (zero-width, directional overrides, etc.)
# Cc (control chars) intentionally excluded — it includes \n \r \t
_INVISIBLE_CATEGORIES = frozenset({"Cf"})
_INVISIBLE_CODEPOINTS = frozenset(
    {
        0x00AD,  # soft hyphen
        0x200B,  # zero-width space
        0x200C,  # zero-width non-joiner
        0x200D,  # zero-width joiner
        0x2060,  # word joiner
        0xFEFF,  # zero-width no-break space / BOM
    }
)


def _resolve_device() -> int:
    """
    Return the transformers pipeline device index.

    ``config.SCANNER_DEVICE`` wins when set. Otherwise auto-detect: the CUDA
    image ships a CUDA torch build and lands on GPU 0, while the CPU image
    ships the CPU-only wheel, reports ``is_available()`` False, and stays on -1.
    """
    if config.SCANNER_DEVICE:
        return int(config.SCANNER_DEVICE)
    return 0 if torch.cuda.is_available() else -1


def _is_int(value) -> bool:
    """Return True for ints, excluding bools."""
    return isinstance(value, int) and not isinstance(value, bool)


@dataclass
class ScanResult:
    """Result from a single scanner."""

    scanner: str
    is_safe: bool
    score: float
    reason: str | None = None


class PromptInjectionScanner:
    """Detects prompt injection using a HuggingFace text-classification model."""

    def __init__(self, **kwargs):
        """
        Initialise the scanner from keyword arguments.

        Kwargs:
            model (str): HuggingFace model ID. Defaults to config.DEFAULT_MODEL.
            injection_label (str): Positive-class label. Defaults to config.DEFAULT_INJECTION_LABEL.
            threshold (float): Block threshold [0,1]. Defaults to config.DEFAULT_THRESHOLD.
            match_type (str): ``"full"``, ``"sentence"`` or ``"sliding_window"``. Defaults to ``"full"``.
            model_max_length (int): Max token length, special tokens included, up to the model's limit.
                Defaults to 512.
            window_overlap (int): Tokens shared by consecutive windows in ``"sliding_window"`` mode.
                Defaults to a quarter of the window.
            window_batch_size (int): Windows scored per model call in ``"sliding_window"`` mode. Defaults to 8.
            max_windows (int): Most windows one input may span in ``"sliding_window"`` mode. Input spanning
                more is blocked with score 1.0. Defaults to 64.
        """
        self._model = kwargs.get("model", "") or config.DEFAULT_MODEL
        self._injection_label = kwargs.get("injection_label", "") or config.DEFAULT_INJECTION_LABEL
        threshold = kwargs.get("threshold")
        self._threshold = config.DEFAULT_THRESHOLD if threshold is None else threshold
        self._match_type = kwargs.get("match_type", "full")
        self._model_max_length = kwargs.get("model_max_length", 512)
        self._window_overlap: int | None = kwargs.get("window_overlap")
        self._window_batch_size = kwargs.get("window_batch_size", 8)
        self._max_windows = kwargs.get("max_windows", 64)
        self._pipe: Pipeline | None = None
        self._injection_label_missing_warned = False

    def load(self):
        """Load the HuggingFace pipeline and validate the injection label exists."""
        if self._match_type == "sliding_window":
            self._check_window_params()
        device = _resolve_device()
        # Device goes in msg, not extra: the logging.basicConfig format in
        # main.py only renders %(message)s, so extra= fields never surface.
        logger.info("loading model on device %s", device, extra={"model": self._model})
        self._pipe = pipeline(
            "text-classification",
            model=self._model,
            device=device,
            truncation=True,
            max_length=self._model_max_length,
            top_k=None,
        )
        self._check_model_limit()
        if self._match_type == "sliding_window":
            self._configure_windows()
        known_labels = self._known_labels()
        if known_labels and self._injection_label not in known_labels:
            raise RuntimeError(f"injection_label {self._injection_label!r} not in model labels: {known_labels}")
        if not known_labels:
            # Some models populate only one of label2id/id2label, or neither
            # (e.g. generic LABEL_0/LABEL_1). Can't validate up front; the
            # label is resolved per-inference from pipeline output instead.
            logger.warning(
                "model exposes no label map; skipping injection_label validation",
                extra={"injection_label": self._injection_label},
            )
        logger.info("model ready")

    def _check_window_params(self):
        """Reject sliding-window params that are not positive ints, before the model loads."""
        for name in ("model_max_length", "window_batch_size", "max_windows"):
            value = getattr(self, f"_{name}")
            if not _is_int(value) or value < 1:
                raise ValueError(f"{name} must be a positive int, got {value!r}")
        if self._window_overlap is not None and not _is_int(self._window_overlap):
            raise ValueError(f"window_overlap must be an int, got {self._window_overlap!r}")

    def _configure_windows(self):
        """Check the tokenizer can build token-ID windows and validate the overlap against the window size."""
        tokenizer = self._pipe.tokenizer
        if not getattr(tokenizer, "is_fast", False):
            raise ValueError(f"sliding_window needs a fast tokenizer; {self._model!r} has none")
        if self._window_batch_size > 1 and tokenizer.pad_token is None:
            raise ValueError(f"window_batch_size > 1 needs a pad token; {self._model!r} has none")
        span = self._model_max_length - tokenizer.num_special_tokens_to_add(pair=False)
        if span < 1:
            raise ValueError(f"model_max_length {self._model_max_length} leaves no room beside the special tokens")
        if self._window_overlap is None:
            self._window_overlap = span // 4
        if not 0 <= self._window_overlap < span:
            raise ValueError(f"window_overlap {self._window_overlap} must be >= 0 and < the window of {span} tokens")
        self._check_overflow_windows(span)

    def _check_model_limit(self):
        """Reject a model_max_length above the model's position embeddings or the tokenizer's max length."""
        limits = (
            getattr(self._pipe.model.config, "max_position_embeddings", None),
            getattr(self._pipe.tokenizer, "model_max_length", None),
        )
        limit = min((n for n in limits if _is_int(n)), default=None)
        if limit is not None and _is_int(self._model_max_length) and self._model_max_length > limit:
            raise ValueError(f"model_max_length {self._model_max_length} exceeds the model limit of {limit} tokens")

    def _check_overflow_windows(self, span: int):
        """Check the tokenizer splits a probe text longer than one window into windows overlapping by window_overlap."""
        tokenizer = self._pipe.tokenizer
        step = span - self._window_overlap
        # At least three windows, and past max_length so a tokenizer that stops reading there is caught.
        length = max(span + step, self._model_max_length + 16) + 1
        probe = " ".join(f"w{i}" for i in range(length))
        encoded = tokenizer(probe, add_special_tokens=False, return_offsets_mapping=True, verbose=False)
        probe = probe[: encoded["offset_mapping"][length - 1][1]]
        full = tokenizer(probe, add_special_tokens=False, verbose=False)["input_ids"]
        expected = [full[start : start + span] for start in range(0, max(len(full) - self._window_overlap, 1), step)]
        enc = self._encode_windows(probe, return_special_tokens_mask=True)
        windows = [
            [i for i, special in zip(ids, mask, strict=True) if not special]
            for ids, mask in zip(enc["input_ids"], enc["special_tokens_mask"], strict=True)
        ]
        if windows != expected:
            raise RuntimeError(
                f"tokenizer overflow windows do not continue the input with overlap {self._window_overlap}; "
                "tokenizers 0.23.3 or later is required"
            )

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
        results = self._pipe(text)
        return self._injection_score(results[0] if results and isinstance(results[0], list) else results)

    def _injection_score(self, label_scores: list) -> float:
        """Pick the injection label's score out of one pipeline result."""
        scores = {r["label"]: r["score"] for r in label_scores}
        if self._injection_label not in scores and not self._injection_label_missing_warned:
            logger.warning(
                "injection_label not in model output",
                extra={"injection_label": self._injection_label, "model_labels": sorted(scores.keys())},
            )
            self._injection_label_missing_warned = True
        return scores.get(self._injection_label, 0.0)

    @staticmethod
    def _split_sentences(text: str) -> list:
        """Split text into sentences on .  !  ? boundaries."""
        parts = re.split(r"(?<=[.!?])\s+", text.strip())
        return [p for p in parts if p]

    def _encode_windows(self, text: str, **kwargs):
        """Tokenize text into overlapping rows of at most model_max_length tokens each."""
        return self._pipe.tokenizer(
            text,
            truncation=True,
            max_length=self._model_max_length,
            stride=self._window_overlap,
            return_overflowing_tokens=True,
            **kwargs,
        )

    def _split_windows(self, text: str) -> list:
        """Tokenize text once into overlapping model inputs of at most model_max_length tokens each."""
        enc = self._encode_windows(text)
        enc.pop("overflow_to_sample_mapping", None)
        return [{key: rows[i] for key, rows in enc.items()} for i in range(len(enc["input_ids"]))]

    def _score_windows(self, windows: list) -> float:
        """Return the highest injection score across windows, scoring window_batch_size of them per model call."""
        best = 0.0
        for start in range(0, len(windows), self._window_batch_size):
            batch = self._pipe.tokenizer.pad(windows[start : start + self._window_batch_size], return_tensors="pt")
            logits = self._pipe.forward(dict(batch))["logits"]
            for row in logits:
                best = max(best, self._injection_score(self._pipe.postprocess({"logits": row[None]}, top_k=None)))
        return best

    def scan(self, text: str) -> ScanResult:
        """
        Scan text for prompt injection.

        Returns:
            ScanResult with is_safe=True if injection score is below threshold.
        """
        if self._pipe is None:
            raise RuntimeError("PromptInjectionScanner not loaded; call load() first")
        if self._match_type == "sentence":
            sentences = self._split_sentences(text) or [text]
            injection_score = max(self._score_text(s) for s in sentences)
        elif self._match_type == "sliding_window":
            windows = self._split_windows(text)
            if len(windows) > self._max_windows:
                logger.warning("input spans %d windows, over max_windows %d; blocking", len(windows), self._max_windows)
                return ScanResult(
                    scanner="PromptInjection",
                    is_safe=False,
                    score=1.0,
                    reason=f"input spans {len(windows)} windows, over max_windows {self._max_windows}",
                )
            injection_score = self._score_windows(windows)
        else:
            injection_score = self._score_text(text)

        is_safe = injection_score < self._threshold
        return ScanResult(
            scanner="PromptInjection",
            is_safe=is_safe,
            score=round(injection_score, 4),
            reason=None if is_safe else (f"injection score {injection_score:.4f} >= {self._threshold}"),
        )


class RegexScanner:
    """Blocks text matching configurable regex patterns (e.g. credential leakage)."""

    def __init__(
        self,
        patterns: list | None = None,
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
            elif not matched:
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
            ch for ch in text if ord(ch) in _INVISIBLE_CODEPOINTS or unicodedata.category(ch) in _INVISIBLE_CATEGORIES
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
