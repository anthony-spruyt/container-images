"""Adapts the PromptInjection scanner to the service's scan function."""

import re
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

    def __init__(self, scanner: Any, model: str, *, locate: Callable[[str, str], Any] = _hub_lookup):
        """Wrap a scanner exposing load() and scan(text); locate finds a model file in the Hub cache."""
        self._scanner = scanner
        self._model = model
        self._locate = locate
        self.revision = ""

    def load(self) -> None:
        """Load the model and record the cached snapshot it was loaded from."""
        self._scanner.load()
        path = self._locate(self._model, "config.json")
        self.revision = PurePath(path).parent.name if isinstance(path, str) else ""

    def __call__(self, text: str) -> bool:
        """Return True when the scanner finds text unsafe."""
        return not self._scanner.scan(model_input(text)).is_safe
