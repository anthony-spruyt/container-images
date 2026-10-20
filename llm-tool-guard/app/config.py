"""Service configuration, read from the environment.

The module-level DEFAULT_* names and SCANNER_DEVICE are the fallbacks scanner_types.py reads.
"""

import math
import os
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Self
from urllib.parse import urlsplit

DEFAULT_MODEL = "Horizon-Labs/prompt-injection-guard-base"
DEFAULT_INJECTION_LABEL = "INJECTION"
DEFAULT_THRESHOLD = 0.9
_JEV_MODEL = "jev-1.13.0"
_JEV_MODES = ("off", "enforce")
_PRINTABLE_ASCII = re.compile(r"[!-~]*")
SCANNER_DEVICE = os.environ.get("SCANNER_DEVICE", "")

# [CLS] and [SEP]: the tokens each window spends outside the text.
_SPECIAL_TOKENS = 2


def _number[T: (int, float)](env: Mapping[str, str], name: str, default: T, parse: Callable[[str], T], low: T) -> T:
    raw = env.get(name, "")
    if not raw:
        return default
    try:
        value = parse(raw)
    except ValueError:
        raise ValueError(f"{name} must be a number, got {raw!r}") from None
    if math.isnan(value) or value < low:
        raise ValueError(f"{name} must be at least {low}, got {raw!r}")
    return value


def _is_base_url(value: str) -> bool:
    if not _PRINTABLE_ASCII.fullmatch(value) or "?" in value or "#" in value:
        return False
    try:
        parts = urlsplit(value)
        port = parts.port
    except ValueError:
        return False
    return (
        parts.scheme in ("http", "https")
        and bool(parts.hostname)
        and "@" not in parts.netloc
        and (port is None or port > 0)
    )


def _jev_endpoint(env: Mapping[str, str], mode: str) -> tuple[str, str]:
    """Return the Jev API base URL and key, each required when mode is enforce; neither value is echoed in errors."""
    key = env.get("JEV_API_KEY", "")
    if mode == "enforce" and not key:
        raise ValueError("JEV_API_KEY is required when JEV_MODE=enforce")
    if not _PRINTABLE_ASCII.fullmatch(key):
        raise ValueError("JEV_API_KEY must be printable ASCII with no spaces or line breaks")
    api_url = env.get("JEV_API_URL", "")
    if mode == "enforce" and not api_url:
        raise ValueError("JEV_API_URL is required when JEV_MODE=enforce")
    if api_url and not _is_base_url(api_url):
        raise ValueError(
            "JEV_API_URL must be an absolute http(s) URL of printable ASCII with no spaces or line breaks, "
            "a valid port, and no user info, query or fragment"
        )
    return api_url.rstrip("/"), key


def _jev_settings(env: Mapping[str, str]) -> dict:
    """Read the Jev settings as Settings keyword arguments, checked against each other."""
    mode = env.get("JEV_MODE") or "off"
    if mode not in _JEV_MODES:
        raise ValueError(f"JEV_MODE must be one of {', '.join(_JEV_MODES)}, got {mode!r}")
    api_url, key = _jev_endpoint(env, mode)
    block_at = _number(env, "JEV_BLOCK_AT", 0.90, float, 0.0)
    if not 0 < block_at <= 1:
        raise ValueError(f"JEV_BLOCK_AT must be in (0, 1], got {block_at}")
    clear_below = _number(env, "JEV_CLEAR_BELOW", 0.08, float, 0.0)
    if clear_below > block_at:
        raise ValueError(f"JEV_CLEAR_BELOW must not exceed JEV_BLOCK_AT, got {clear_below} above {block_at}")
    return {
        "jev_mode": mode,
        "jev_api_key": key,
        "jev_api_url": api_url,
        "jev_model": env.get("JEV_MODEL") or _JEV_MODEL,
        "jev_block_at": block_at,
        "jev_clear_below": clear_below,
        "jev_timeout_seconds": _number(env, "JEV_TIMEOUT_SECONDS", 10.0, float, 0.001),
        "jev_max_text_bytes": _number(env, "JEV_MAX_TEXT_BYTES", 16 * 1024, int, 1),
    }


@dataclass(frozen=True)
class Settings:
    """Runtime settings; secrets are left out of repr."""

    listen_host: str
    listen_port: int
    model: str
    injection_label: str
    threshold: float
    window_tokens: int
    window_overlap: int
    window_batch_size: int
    max_windows: int
    max_text_bytes: int
    max_body_bytes: int
    scan_workers: int
    max_pending_scans: int
    max_concurrent_requests: int
    scan_timeout_seconds: float
    shutdown_drain_seconds: float
    valkey_url: str = field(repr=False)
    valkey_username: str
    valkey_password: str = field(repr=False)
    valkey_timeout_seconds: float
    cache_ttl_seconds: int
    auth_token: str = field(repr=False)
    jev_mode: str
    jev_api_key: str = field(repr=False)
    jev_api_url: str
    jev_model: str
    jev_block_at: float
    jev_clear_below: float
    jev_timeout_seconds: float
    jev_max_text_bytes: int

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> Self:
        """Read settings from env, raising ValueError naming the first invalid variable."""
        threshold = _number(env, "THRESHOLD", DEFAULT_THRESHOLD, float, 0.0)
        if not 0 < threshold <= 1:
            raise ValueError(f"THRESHOLD must be in (0, 1], got {threshold}")
        window_tokens = _number(env, "WINDOW_TOKENS", 2048, int, _SPECIAL_TOKENS + 1)
        span = window_tokens - _SPECIAL_TOKENS
        window_overlap = _number(env, "WINDOW_OVERLAP", 512, int, 0)
        if window_overlap >= span:
            raise ValueError(f"WINDOW_OVERLAP must be below the {span}-token window, got {window_overlap}")
        max_text_bytes = _number(env, "MAX_TEXT_BYTES", 256 * 1024, int, 1)
        # Byte-level BPE yields at most one token per byte, so this covers any text within MAX_TEXT_BYTES.
        covering = 1 + math.ceil(max(0, max_text_bytes - span) / (span - window_overlap))
        return cls(
            listen_host=env.get("LISTEN_HOST") or "0.0.0.0",
            listen_port=_number(env, "LISTEN_PORT", 8080, int, 1),
            model=env.get("MODEL") or DEFAULT_MODEL,
            injection_label=env.get("INJECTION_LABEL") or DEFAULT_INJECTION_LABEL,
            threshold=threshold,
            window_tokens=window_tokens,
            window_overlap=window_overlap,
            window_batch_size=_number(env, "WINDOW_BATCH_SIZE", 1, int, 1),
            max_windows=_number(env, "MAX_WINDOWS", covering, int, 1),
            max_text_bytes=max_text_bytes,
            max_body_bytes=_number(env, "MAX_BODY_BYTES", 8 * 1024 * 1024, int, 1),
            scan_workers=_number(env, "SCAN_WORKERS", 1, int, 1),
            max_pending_scans=_number(env, "MAX_PENDING_SCANS", 128, int, 1),
            max_concurrent_requests=_number(env, "MAX_CONCURRENT_REQUESTS", 8, int, 1),
            scan_timeout_seconds=_number(env, "SCAN_TIMEOUT_SECONDS", 300.0, float, 0.001),
            shutdown_drain_seconds=_number(env, "SHUTDOWN_DRAIN_SECONDS", 20.0, float, 0.0),
            valkey_url=env.get("VALKEY_URL", ""),
            valkey_username=env.get("VALKEY_USERNAME", ""),
            valkey_password=env.get("VALKEY_PASSWORD", ""),
            valkey_timeout_seconds=_number(env, "VALKEY_TIMEOUT_SECONDS", 0.5, float, 0.001),
            cache_ttl_seconds=_number(env, "CACHE_TTL_SECONDS", 30 * 24 * 3600, int, 1),
            auth_token=env.get("AUTH_TOKEN", ""),
            **_jev_settings(env),
        )
