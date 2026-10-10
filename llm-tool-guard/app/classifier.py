"""Adapts the PromptInjection scanner to the service's scan function."""

import re
import threading
import time
from collections.abc import Callable
from pathlib import PurePath
from typing import Any

_SURROGATE = re.compile("[\ud800-\udfff]")


def model_input(text: str) -> str:
    """Replace lone surrogates, which the tokenizer cannot encode, with U+FFFD."""
    return _SURROGATE.sub("\ufffd", text)


def _hub_lookup(model: str, filename: str) -> Any:
    from huggingface_hub import try_to_load_from_cache

    return try_to_load_from_cache(model, filename)


class Classifier:
    """Blocking scan function over a PromptInjectionScanner: True means flagged."""

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
        self.revision = ""

    def load(self) -> None:
        """Load the model and record the cached snapshot it was loaded from."""
        self._scanner.load()
        if self._budget is not None:
            self._enforce_budget()
        path = self._locate(self._model, "config.json")
        self.revision = PurePath(path).parent.name if isinstance(path, str) else ""

    def _enforce_budget(self) -> None:
        """Check the calling thread's deadline before each model call; a running forward pass cannot be interrupted."""
        pipe = self._scanner._pipe
        forward = pipe.forward

        def bounded(*args: Any, **kwargs: Any) -> Any:
            deadline = getattr(self._local, "deadline", None)
            if deadline is not None and time.monotonic() >= deadline:
                raise TimeoutError(f"scan over its {self._budget}s time budget")
            return forward(*args, **kwargs)

        pipe.forward = bounded

    def __call__(self, text: str) -> bool:
        """Return True when the scanner finds text unsafe."""
        if self._budget is not None:
            self._local.deadline = time.monotonic() + self._budget
        try:
            return not self._scanner.scan(model_input(text)).is_safe
        finally:
            self._local.deadline = None
