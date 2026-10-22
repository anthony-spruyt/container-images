# renovate: datasource=docker depName=python
ARG PYTHON_VERSION=3.14-slim@sha256:fbecd461fc72d21b2143c6eaba25143738079154a6d0ea3da3aec724f50eed4a
FROM ghcr.io/astral-sh/uv:0.13.5@sha256:32a7bb39b496babbd997b0a39a4d66c126bdaf5661b302bf6f06abda8deca6ff AS uv
FROM python:${PYTHON_VERSION} AS torch-lock
WORKDIR /lock
# Built from the llm-guard/ build context (metadata.yaml build_context): pyproject.toml, uv.lock and app/ are shared with the CPU image.
COPY pyproject.toml uv.lock ./
# Hashed export of only cu130 torch and its dependencies: unchanged while app pins change, so the torch layer stays cached.
RUN --mount=from=uv,source=/uv,target=/usr/local/bin/uv \
    uv export --locked --no-dev --only-group cu130 --format pylock.toml --output-file pylock.torch.toml

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
    uv sync --locked --no-build --no-dev --inexact --group cu130

COPY app/ .

# Model weights are not baked in: mount a persistent volume at HF_HOME so the first-load download survives restarts.
ENV HF_HOME=/app/.cache/huggingface

RUN useradd -u 1000 -m appuser && chown -R 1000:1000 /app
USER 1000:1000

ENV CONFIG_FILE=/app/default-scanners.yml
ENV LISTEN_HOST=0.0.0.0
ENV LISTEN_PORT=8080

EXPOSE 8080

HEALTHCHECK NONE

CMD ["python", "main.py"]
