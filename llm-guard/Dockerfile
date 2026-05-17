# renovate: datasource=docker depName=laiyer/llm-guard-api
ARG UPSTREAM_VERSION=0.3.16
FROM laiyer/llm-guard-api:${UPSTREAM_VERSION}

# Pre-download PromptInjection model at build time to avoid ~300s startup delay
# hadolint ignore=DL3059
RUN python -c "from transformers import AutoModelForSequenceClassification, AutoTokenizer; model = 'protectai/deberta-v3-base-prompt-injection-v2'; AutoModelForSequenceClassification.from_pretrained(model); AutoTokenizer.from_pretrained(model)"

USER 1000:1000
HEALTHCHECK NONE
