# renovate: datasource=docker depName=python
ARG PYTHON_VERSION=3.14-slim@sha256:fbecd461fc72d21b2143c6eaba25143738079154a6d0ea3da3aec724f50eed4a
FROM docker.io/astral/uv:0.13.5@sha256:32a7bb39b496babbd997b0a39a4d66c126bdaf5661b302bf6f06abda8deca6ff AS uv
FROM python:${PYTHON_VERSION} AS torch-lock
WORKDIR /lock
COPY pyproject.toml uv.lock ./
# Hashed export of only cpu torch and its dependencies: unchanged while app pins change, so the torch layer stays cached.
RUN --mount=from=uv,source=/uv,target=/usr/local/bin/uv \
    uv export --locked --no-dev --only-group cpu --format pylock.toml --output-file pylock.torch.toml

FROM python:${PYTHON_VERSION}

WORKDIR /app

# Build-time only (ARG): uv installs into the image's Python.
ARG UV_PROJECT_ENVIRONMENT=/usr/local UV_PYTHON_DOWNLOADS=never UV_NO_CACHE=1 UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1

COPY --from=torch-lock /lock/pylock.torch.toml /tmp/pylock.torch.toml
RUN --mount=from=uv,source=/uv,target=/usr/local/bin/uv \
    uv pip install --system --require-hashes --no-build --no-deps -r /tmp/pylock.torch.toml \
    && rm /tmp/pylock.torch.toml

COPY pyproject.toml uv.lock ./
# Nothing installs packages at runtime, so pip stays out of the image.
RUN --mount=from=uv,source=/uv,target=/usr/local/bin/uv \
    uv sync --locked --no-build --no-dev --group cpu \
    && uv pip uninstall --system pip \
    && rm -f /usr/local/bin/pip

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
