# renovate: datasource=docker depName=python
ARG PYTHON_VERSION=3.14-slim@sha256:a2b82f3c48559aa0a8446d9af49826b6e2b2016f4cd2afabfe6013ec53729170
FROM python:${PYTHON_VERSION}

WORKDIR /app

# torch comes from its own requirements file because --index-url replaces PyPI,
# and the PyTorch index does not serve the other dependencies.
# --only-binary :all: fails the build on a missing wheel instead of running a setup.py.
COPY app/requirements-cpu.txt .
RUN pip install --no-cache-dir --only-binary :all: -r requirements-cpu.txt

COPY app/requirements.txt .
RUN pip install --no-cache-dir --only-binary :all: -r requirements.txt

COPY app/ .

# Model weights are not baked in: mount a volume at HF_HOME. Set HF_HUB_OFFLINE=1 once the cache is warm.
ENV HF_HOME=/app/.cache/huggingface

RUN useradd -u 1000 -m appuser && mkdir -p "$HF_HOME" && chown -R 1000:1000 /app
USER 1000:1000

ENV LISTEN_HOST=0.0.0.0
ENV LISTEN_PORT=8080

EXPOSE 8080

HEALTHCHECK NONE

CMD ["python", "main.py"]
