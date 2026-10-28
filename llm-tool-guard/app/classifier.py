"""Adapts the PromptInjection scanner to the service's scan function."""

import re
import threading
import time
from collections.abc import Callable
from pathlib import PurePath
from typing import Any

from guard import ScanStoppedError

_SURROGATE = re.compile("[\ud800-\udfff]")


def model_input(text: str) -> str:
    """Replace lone surrogates, which the tokenizer cannot encode, with U+FFFD, one for one: spans index either text."""
    return _SURROGATE.sub("\ufffd", text)


def _hub_lookup(model: str, filename: str) -> Any:
    from huggingface_hub import try_to_load_from_cache

    return try_to_load_from_cache(model, filename)


class Classifier:
    """Blocking scan function over a PromptInjectionScanner, returning (flagged, score, flagged_spans)."""

    def __init__(
        self,
        scanner: Any,
        model: str,
        *,
        locate: Callable[[str, str], Any] = _hub_lookup,
        time_budget_seconds: float | None = None,
    ):
        """Wrap a scanner exposing load() and scan(text); locate finds a model file in the Hub cache.

        A scan that runs past time_budget_seconds raises TimeoutError before its next window; None means no budget.
        """
        self._scanner = scanner
        self._model = model
        self._locate = locate
        self._budget = time_budget_seconds
        self._local = threading.local()
        self._stopped = threading.Event()
        self.revision = ""

    def load(self) -> None:
        """Load the model and record the cached snapshot it was loaded from."""
        self._scanner.load()
        self._guard_windows()
        path = self._locate(self._model, "config.json")
        self.revision = PurePath(path).parent.name if isinstance(path, str) else ""

    def stop(self) -> None:
        """Make every scan, running or later, raise ScanStoppedError before its next window."""
        self._stopped.set()

    def _guard_windows(self) -> None:
        """Check the stop flag and the thread's deadline before each model call; a running pass cannot be stopped."""
        pipe = self._scanner._pipe
        forward = pipe.forward

        def bounded(*args: Any, **kwargs: Any) -> Any:
            if self._stopped.is_set():
                raise ScanStoppedError("scan stopped")
            deadline = getattr(self._local, "deadline", None)
            if deadline is not None and time.monotonic() >= deadline:
                raise TimeoutError(f"scan over its {self._budget}s time budget")
            return forward(*args, **kwargs)

        pipe.forward = bounded

    def __call__(self, text: str) -> tuple[bool, float, tuple[tuple[int, int], ...]]:
        """Return (flagged, score, flagged_spans), each as the scanner reports it; flagged when it finds text unsafe.

        flagged_spans are the character spans of text for the windows that scored at or above the threshold.
        """
        if self._budget is not None:
            self._local.deadline = time.monotonic() + self._budget
        try:
            result = self._scanner.scan(model_input(text))
            return not result.is_safe, float(result.score), tuple(result.flagged_spans)
        finally:
            self._local.deadline = None
