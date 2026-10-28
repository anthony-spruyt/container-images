# renovate: datasource=docker depName=python
ARG PYTHON_VERSION=3.14-slim@sha256:82abc9f53600280b0757126f83c5a7d47088592d2acb6b4c0b9e97f76865508c
# renovate: datasource=github-releases depName=intel/compute-runtime versioning=loose
ARG COMPUTE_RUNTIME_VERSION=26.35.39758.10
ARG GMMLIB_VERSION=22.10.0
ARG IGC_VERSION=2.41.5
ARG IGC_BUILD=22716

FROM docker.io/astral/uv:0.13.5@sha256:32a7bb39b496babbd997b0a39a4d66c126bdaf5661b302bf6f06abda8deca6ff AS uv

# The OpenCL driver, its compiler and its memory library, each checksummed. Bump them together: the driver package
# depends on the one IGC release it pairs with (see its Depends), and the apt install in the final stage fails otherwise.
FROM scratch AS gpu-debs
ARG COMPUTE_RUNTIME_VERSION
ARG GMMLIB_VERSION
ARG IGC_VERSION
ARG IGC_BUILD
ADD --checksum=sha256:61712caaddeba3d38e4f79e2a0fb23fea25596ca2d72c3144c6eea2331ec4301 \
    https://github.com/intel/compute-runtime/releases/download/${COMPUTE_RUNTIME_VERSION}/intel-opencl-icd_${COMPUTE_RUNTIME_VERSION}-0_amd64.deb /
ADD --checksum=sha256:6031a63d6e8a12ce61c14efc15f2c8e727061286e3820b8594e6d00615e04d54 \
    https://github.com/intel/compute-runtime/releases/download/${COMPUTE_RUNTIME_VERSION}/libigdgmm12_${GMMLIB_VERSION}_amd64.deb /
ADD --checksum=sha256:0a6e64a663ae65a0fa02d6912ae3b6b37cf85b90c21cc423fd9fef70aaf4f628 \
    https://github.com/intel/intel-graphics-compiler/releases/download/v${IGC_VERSION}/intel-igc-core-2_${IGC_VERSION}+${IGC_BUILD}_amd64.deb /
ADD --checksum=sha256:779e1b9e88098eb25711e9a8f67c2752665bad22f134aa40ed5649f6e1b87058 \
    https://github.com/intel/intel-graphics-compiler/releases/download/v${IGC_VERSION}/intel-igc-opencl-2_${IGC_VERSION}+${IGC_BUILD}_amd64.deb /

FROM python:${PYTHON_VERSION}

ARG COMPUTE_RUNTIME_VERSION
ARG GMMLIB_VERSION
ARG IGC_VERSION
ARG IGC_BUILD

WORKDIR /app

# Debian packages no IGC and its compute-runtime is too old, so the Intel debs come from the pinned releases above.
RUN --mount=type=bind,from=gpu-debs,target=/debs \
    apt-get update \
    && apt-get install -y --no-install-recommends ocl-icd-libopencl1 /debs/*.deb \
    && rm -rf /var/lib/apt/lists/*

# Build-time only (ARG): uv installs into the image's Python.
ARG UV_PROJECT_ENVIRONMENT=/usr/local UV_PYTHON_DOWNLOADS=never UV_NO_CACHE=1 UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1

COPY pyproject.toml uv.lock ./
# Nothing installs packages at runtime, so pip stays out of the image.
RUN --mount=from=uv,source=/uv,target=/usr/local/bin/uv \
    uv sync --locked --no-build --no-dev \
    && uv pip uninstall --system pip \
    && rm -f /usr/local/bin/pip

COPY app/ .

# Model weights are not baked in: mount the llm-tool-guard-model image at HF_HOME/hub, with a writable volume at HF_HOME.
ENV HF_HOME=/app/.cache/huggingface
# The driver keeps its compiler cache in $XDG_CACHE_HOME/neo_compiler_cache and skips the cache when that parent is missing.
ENV XDG_CACHE_HOME=$HF_HOME
# Part of the verdict cache namespace: a different driver can score a window differently.
ENV INTEL_GPU_RUNTIME="compute-runtime ${COMPUTE_RUNTIME_VERSION}, igc ${IGC_VERSION}+${IGC_BUILD}, gmmlib ${GMMLIB_VERSION}"

RUN useradd -u 1000 -m appuser && mkdir -p "$HF_HOME" && chown -R 1000:1000 /app
USER 1000:1000

ENV LISTEN_HOST=0.0.0.0
ENV LISTEN_PORT=8080

EXPOSE 8080

HEALTHCHECK NONE

CMD ["python", "main.py"]
