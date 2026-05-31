"""Configuration from environment variables."""
import os


MODEL = os.environ.get("MODEL", "protectai/deberta-v3-base-prompt-injection-v2")
INJECTION_LABEL = os.environ.get("INJECTION_LABEL", "INJECTION")


def _parse_threshold() -> float:
    """Parse and validate THRESHOLD env var."""
    raw = os.environ.get("THRESHOLD", "0.5")
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"THRESHOLD must be a float between 0 and 1, got: {raw!r}") from exc
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"THRESHOLD must be between 0 and 1, got: {value}")
    return value


THRESHOLD = _parse_threshold()
LISTEN_HOST = os.environ.get("LISTEN_HOST", "0.0.0.0")
LISTEN_PORT = int(os.environ.get("LISTEN_PORT", "8080"))
