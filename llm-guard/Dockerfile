# renovate: datasource=docker depName=python
ARG PYTHON_VERSION=3.12-slim
FROM python:${PYTHON_VERSION}

ARG MODEL=protectai/deberta-v3-base-prompt-injection-v2

WORKDIR /app

COPY app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ .

ENV HF_HOME=/app/.cache/huggingface

# Pre-download model into HF cache
COPY assets/download_model.py /tmp/download_model.py
RUN MODEL=${MODEL} python /tmp/download_model.py && rm /tmp/download_model.py

RUN useradd -u 1000 -m appuser && chown -R 1000:1000 /app
USER 1000:1000

ENV MODEL=${MODEL}
ENV INJECTION_LABEL=INJECTION
ENV THRESHOLD=0.5
ENV LISTEN_HOST=0.0.0.0
ENV LISTEN_PORT=8080

EXPOSE 8080

HEALTHCHECK NONE

CMD ["python", "main.py"]
