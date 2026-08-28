# renovate: datasource=docker depName=python
ARG PYTHON_VERSION=3.14-slim@sha256:cae66f2ef0ec51a9891263eeee7f987dacf0a9879e8aa9353d5606e0530619a5
FROM python:${PYTHON_VERSION}

WORKDIR /app

# torch is installed first and from its own requirements file: --index-url
# replaces PyPI wholesale, and the PyTorch index does not serve fastapi,
# uvicorn, transformers or pyyaml. Torch first also keeps the largest, most
# cache-stable layer at the bottom and splits what used to be one 2.7GB layer
# into two, which containerd can pull in parallel.
# --only-binary :all: refuses source distributions outright: every dependency
# here publishes a cp314/abi3 manylinux wheel, so a missing wheel means a
# resolution mistake and should fail the build rather than silently run an
# arbitrary setup.py at image-build time.
COPY app/requirements-cpu.txt .
RUN pip install --no-cache-dir --only-binary :all: -r requirements-cpu.txt

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
