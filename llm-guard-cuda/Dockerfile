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
# The torch lock is not re-locked when this one changes, so pip check fails the build if the two layers disagree.
RUN pip install --no-cache-dir --only-binary :all: --require-hashes -r requirements.txt \
    && pip check

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
