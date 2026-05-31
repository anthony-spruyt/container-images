import os


MODEL = os.environ.get("MODEL", "protectai/deberta-v3-base-prompt-injection-v2")
INJECTION_LABEL = os.environ.get("INJECTION_LABEL", "INJECTION")
THRESHOLD = float(os.environ.get("THRESHOLD", "0.5"))
LISTEN_HOST = os.environ.get("LISTEN_HOST", "0.0.0.0")
LISTEN_PORT = int(os.environ.get("LISTEN_PORT", "8080"))
