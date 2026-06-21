# renovate: datasource=docker depName=python
ARG PYTHON_VERSION=3.14-slim@sha256:44dd04494ee8f3b538294360e7c4b3acb87c8268e4d0a4828a6500b1eff50061
FROM python:${PYTHON_VERSION}

WORKDIR /app

COPY app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

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
