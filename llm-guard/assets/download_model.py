"""Pre-download model into HuggingFace cache at build time."""

import os
from transformers import pipeline

MODEL = os.environ.get("MODEL", "protectai/deberta-v3-base-prompt-injection-v2")

print(f"Downloading model: {MODEL}")
pipeline("text-classification", model=MODEL)
print("Done.")
