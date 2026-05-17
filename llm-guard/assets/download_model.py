"""Pre-download PromptInjection model into HuggingFace cache."""

from transformers import AutoModelForSequenceClassification, AutoTokenizer

MODEL = "protectai/deberta-v3-base-prompt-injection-v2"

AutoModelForSequenceClassification.from_pretrained(MODEL)
AutoTokenizer.from_pretrained(MODEL)
