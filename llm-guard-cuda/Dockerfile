# renovate: datasource=docker depName=python
ARG PYTHON_VERSION=3.14-slim@sha256:ce40764625a4ff50df3548277632e7f96c4e77fe75fa848aae9885476e7df5a4
FROM python:${PYTHON_VERSION}

WORKDIR /app

# Built from the llm-guard/ build context (metadata.yaml build_context), so
# app/ is shared with the CPU image and only the torch requirements file
# differs. torch is installed first and from its own requirements file:
# --index-url replaces PyPI wholesale, and the PyTorch index does not serve
# fastapi, uvicorn, transformers or pyyaml. Torch first also keeps the
# largest, most cache-stable layer at the bottom.
#
# --only-binary :all: refuses source distributions outright: every dependency
# here publishes a cp314/abi3 manylinux wheel, so a missing wheel means a
# resolution mistake and should fail the build rather than silently run an
# arbitrary setup.py at image-build time.
COPY app/requirements-cuda.txt .
RUN pip install --no-cache-dir --only-binary :all: -r requirements-cuda.txt

COPY app/requirements.txt .
RUN pip install --no-cache-dir --only-binary :all: -r requirements.txt

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
