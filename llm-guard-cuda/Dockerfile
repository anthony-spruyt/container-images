# renovate: datasource=docker depName=python
ARG PYTHON_VERSION=3.14-slim@sha256:a2b82f3c48559aa0a8446d9af49826b6e2b2016f4cd2afabfe6013ec53729170
FROM python:${PYTHON_VERSION}

WORKDIR /app

# Built from the llm-guard/ build context (metadata.yaml build_context): app/ is shared with the CPU image, only the torch lock differs.
# torch is installed first, from its own lock, so an app dependency bump does not re-pull its layer.
# --only-binary :all: fails the build on a missing wheel instead of running a setup.py.
# --extra-index-url is safe only because --require-hashes pins exact files; keep the URL equal to torch/cuda/pyproject.toml.
COPY app/requirements-cuda.txt .
RUN pip install --no-cache-dir --only-binary :all: --require-hashes \
    --extra-index-url https://download.pytorch.org/whl/cu130 -r requirements-cuda.txt

COPY app/requirements.txt .
RUN pip install --no-cache-dir --only-binary :all: --require-hashes -r requirements.txt

COPY app/ .

# Model weights are NOT baked in. The scanner downloads them into HF_HOME on
# first load (transformers pipeline() pulls from the Hub when the cache misses)
# and reuses the cache thereafter. Mount a persistent volume at HF_HOME so the
# download survives restarts. Keeping weights out of the image avoids a ~2.9GB
# layer and the slow cold pull it caused on every tag bump.
ENV HF_HOME=/app/.cache/huggingface

RUN useradd -u 1000 -m appuser && chown -R 1000:1000 /app
USER 1000:1000

# Scanner pipeline is configured via CONFIG_FILE (required). Default to the
# baked-in single-scanner config; override by mounting a file and setting
# CONFIG_FILE to its path (e.g. /config/scanners.yml).
ENV CONFIG_FILE=/app/default-scanners.yml
ENV LISTEN_HOST=0.0.0.0
ENV LISTEN_PORT=8080

EXPOSE 8080

HEALTHCHECK NONE

CMD ["python", "main.py"]
