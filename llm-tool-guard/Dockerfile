# renovate: datasource=docker depName=python
ARG PYTHON_VERSION=3.14-slim@sha256:a2b82f3c48559aa0a8446d9af49826b6e2b2016f4cd2afabfe6013ec53729170
FROM ghcr.io/astral-sh/uv:0.13.1@sha256:4a1f3666816dafadd20ceb71eac9a7d56d7ef30279f7d64048519ab901ada336 AS uv
FROM python:${PYTHON_VERSION}

WORKDIR /app

# Installs into the image's Python (--inexact keeps its pip); UV_NO_BUILD fails on a missing wheel instead of running a build script.
ENV UV_PROJECT_ENVIRONMENT=/usr/local UV_PYTHON_DOWNLOADS=never UV_NO_CACHE=1 UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 UV_NO_BUILD=1

COPY pyproject.toml uv.lock ./
# torch gets its own layer, ahead of the app dependencies.
RUN --mount=from=uv,source=/uv,target=/usr/local/bin/uv \
    uv sync --locked --no-dev --inexact --only-group cpu
# hadolint ignore=DL3059
RUN --mount=from=uv,source=/uv,target=/usr/local/bin/uv \
    uv sync --locked --no-dev --inexact --group cpu

COPY app/ .

# Model weights are not baked in: mount a volume at HF_HOME. Set HF_HUB_OFFLINE=1 once the cache is warm.
ENV HF_HOME=/app/.cache/huggingface

RUN useradd -u 1000 -m appuser && mkdir -p "$HF_HOME" && chown -R 1000:1000 /app
USER 1000:1000

ENV LISTEN_HOST=0.0.0.0
ENV LISTEN_PORT=8080

EXPOSE 8080

HEALTHCHECK NONE

CMD ["python", "main.py"]
