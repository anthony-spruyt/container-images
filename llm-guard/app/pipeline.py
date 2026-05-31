"""Scanner pipeline — loads from CONFIG_FILE or ENV defaults."""
import logging
from typing import Optional

import yaml

import config
from scanner_types import InvisibleTextScanner, PromptInjectionScanner, RegexScanner, ScanResult

logger = logging.getLogger(__name__)

_SCANNER_TYPES = {
    "PromptInjection": PromptInjectionScanner,
    "Regex": RegexScanner,
    "InvisibleText": InvisibleTextScanner,
}


def _build_from_config(path: str) -> list:
    """Build scanner list from a YAML config file."""
    with open(path, encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}
    if not isinstance(cfg, dict):
        raise ValueError(f"Config file must be a YAML mapping, got {type(cfg).__name__}")
    scanners = cfg.get("input_scanners", [])
    if not isinstance(scanners, list):
        raise ValueError(f"input_scanners must be a list, got {type(scanners).__name__}")
    scanner_list = []
    seen_names: set = set()
    for i, entry in enumerate(scanners):
        if not isinstance(entry, dict):
            raise ValueError(f"input_scanners[{i}] must be a mapping, got {type(entry).__name__}")
        scanner_type = entry.get("type", "")
        params = entry.get("params") or {}
        cls = _SCANNER_TYPES.get(scanner_type)
        if cls is None:
            raise ValueError(f"Unknown scanner type: {scanner_type!r}")
        if scanner_type in seen_names:
            raise ValueError(f"Duplicate scanner type: {scanner_type!r}")
        seen_names.add(scanner_type)
        scanner_list.append(cls(**params))
    if not scanner_list:
        raise ValueError(f"CONFIG_FILE {path!r} defines no input_scanners")
    return scanner_list


def _build_from_env() -> list:
    """Build default PromptInjection scanner from environment variables."""
    return [PromptInjectionScanner()]


class _Pipeline:
    """Ordered list of scanners run sequentially against each prompt."""

    def __init__(self):
        """Initialise with empty scanner list."""
        self._scanners: list = []

    def load(self):
        """Load all configured scanners."""
        if config.CONFIG_FILE:
            logger.info("loading scanner config", extra={"path": config.CONFIG_FILE})
            self._scanners = _build_from_config(config.CONFIG_FILE)
        else:
            logger.info("no CONFIG_FILE set, using ENV defaults")
            self._scanners = _build_from_env()

        for scanner in self._scanners:
            scanner.load()
        logger.info("pipeline ready", extra={"scanners": len(self._scanners)})

    def scan(self, text: str) -> tuple:
        """
        Run all scanners against text.

        Returns:
            tuple: (is_safe, scores_dict, blocked_reason) where scores_dict maps
            scanner name to float score and blocked_reason is None if safe.
        """
        scores: dict = {}
        blocked_reason: Optional[str] = None
        all_safe = True

        for scanner in self._scanners:
            result: ScanResult = scanner.scan(text)
            scores[result.scanner] = result.score
            if not result.is_safe:
                all_safe = False
                if blocked_reason is None:
                    blocked_reason = result.reason

        return all_safe, scores, blocked_reason


_PIPELINE = _Pipeline()


def load():
    """Load the module-level scanner pipeline."""
    _PIPELINE.load()


def scan(text: str) -> tuple:
    """Run all scanners; return (is_safe, scores_dict, blocked_reason)."""
    return _PIPELINE.scan(text)
