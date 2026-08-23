"""Service configuration.

Scanner behaviour (model, label, threshold, match type, …) is configured
per-scanner in the CONFIG_FILE YAML, NOT via environment variables. The
constants below are only fallback defaults used when a scanner omits the
corresponding param. Only operational settings (bind address, config path)
are read from the environment.
"""
import os


# --- Scanner fallback defaults (overridden per-scanner in CONFIG_FILE) ---
DEFAULT_MODEL = "protectai/deberta-v3-base-prompt-injection-v2"
DEFAULT_INJECTION_LABEL = "INJECTION"
DEFAULT_THRESHOLD = 0.5

# --- Operational settings (environment-driven) ---
CONFIG_FILE = os.environ.get("CONFIG_FILE", "")
LISTEN_HOST = os.environ.get("LISTEN_HOST", "0.0.0.0")
LISTEN_PORT = int(os.environ.get("LISTEN_PORT", "8080"))
# Inference device index passed to the transformers pipeline: "-1" for CPU,
# "0" (or higher) for a specific GPU. Empty means auto-detect — CUDA if the
# installed torch build exposes it, CPU otherwise.
SCANNER_DEVICE = os.environ.get("SCANNER_DEVICE", "")
