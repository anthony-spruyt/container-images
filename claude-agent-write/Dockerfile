# claude-agent-write = claude-agent-read + Go + pre-commit.
# Pinned to a digest by Renovate once claude-agent-read publishes; until then
# :latest resolves the most recent read build.
# renovate: datasource=docker depName=ghcr.io/anthony-spruyt/claude-agent-read versioning=semver
FROM ghcr.io/anthony-spruyt/claude-agent-read:1.0.38@sha256:8492ba5bfb072bdcb3a54bb35ac9330131bd5eb9ba5aa314ee96477645287177

# Ephemeral agent pod — lifespan managed by n8n spawner
HEALTHCHECK NONE

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Go (prebuilt tarball). Root needed to write under /usr/local.
# renovate: depName=golang datasource=docker
ARG GO_VERSION="1.26.3"
USER root
RUN ARCH="$(dpkg --print-architecture)" \
  && curl -fsSL --retry 3 --retry-delay 5 "https://go.dev/dl/go${GO_VERSION}.linux-${ARCH}.tar.gz" | tar -C /usr/local -xz
ENV PATH="/usr/local/go/bin:${PATH}"

# pre-commit (installed for the uid 1000 node user, matching the chain).
# pre-commit builds node/python hook environments at runtime; python3 comes
# from apt in the read base, so there is no fragile from-source Python build.
# renovate: depName=pre-commit datasource=pypi
ARG PRECOMMIT_VERSION="4.6.0"
USER 1000
RUN pip install --no-cache-dir --break-system-packages pre-commit=="${PRECOMMIT_VERSION}"

# Working directory
WORKDIR /workspace
