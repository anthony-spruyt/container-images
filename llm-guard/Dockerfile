# renovate: datasource=docker depName=python
ARG PYTHON_VERSION=3.14-slim@sha256:44dd04494ee8f3b538294360e7c4b3acb87c8268e4d0a4828a6500b1eff50061
FROM python:${PYTHON_VERSION}

ARG MODEL=protectai/deberta-v3-base-prompt-injection-v2

WORKDIR /app

COPY app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ .

ENV HF_HOME=/app/.cache/huggingface

# Pre-download the default model into the HF cache so the image runs offline.
COPY assets/download_model.py /tmp/download_model.py
RUN MODEL=${MODEL} python /tmp/download_model.py && rm /tmp/download_model.py

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
