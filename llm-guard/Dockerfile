# renovate: datasource=docker depName=laiyer/llm-guard-api
ARG UPSTREAM_VERSION=0.3.16
FROM laiyer/llm-guard-api:${UPSTREAM_VERSION}

COPY assets/download_model.py /tmp/download_model.py
RUN python /tmp/download_model.py && rm /tmp/download_model.py

USER 1000:1000
HEALTHCHECK NONE
