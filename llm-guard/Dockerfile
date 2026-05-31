# renovate: datasource=docker depName=python
ARG PYTHON_VERSION=3.14-slim@sha256:c845af9399020c7e562969a13689e929074a10fd057acd1b1fad06a2fb068e97
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
