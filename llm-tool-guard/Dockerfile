# renovate: datasource=docker depName=python
ARG PYTHON_VERSION=3.14-slim@sha256:29e1fe7a54021a1d8990f59223f1246a4239b106895363680b23aa1265f73cb3
FROM ghcr.io/astral-sh/uv:0.13.1@sha256:4a1f3666816dafadd20ceb71eac9a7d56d7ef30279f7d64048519ab901ada336 AS uv
FROM python:${PYTHON_VERSION} AS torch-lock
WORKDIR /lock
COPY pyproject.toml uv.lock ./
# Hashed export of only cpu torch and its dependencies: unchanged while app pins change, so the torch layer stays cached.
RUN --mount=from=uv,source=/uv,target=/usr/local/bin/uv \
    uv export --locked --no-dev --only-group cpu --format pylock.toml --output-file pylock.torch.toml

FROM python:${PYTHON_VERSION}

WORKDIR /app

# Build-time only (ARG): uv installs into the image's Python, and --inexact keeps that Python's pip.
ARG UV_PROJECT_ENVIRONMENT=/usr/local UV_PYTHON_DOWNLOADS=never UV_NO_CACHE=1 UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1

COPY --from=torch-lock /lock/pylock.torch.toml /tmp/pylock.torch.toml
RUN --mount=from=uv,source=/uv,target=/usr/local/bin/uv \
    uv pip install --system --require-hashes --no-build --no-deps -r /tmp/pylock.torch.toml \
    && rm /tmp/pylock.torch.toml

COPY pyproject.toml uv.lock ./
RUN --mount=from=uv,source=/uv,target=/usr/local/bin/uv \
    uv sync --locked --no-build --no-dev --inexact --group cpu

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
