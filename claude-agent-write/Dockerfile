# claude-agent-write = claude-agent-read + Go + pre-commit.
# Pinned to a digest by Renovate once claude-agent-read publishes; until then
# :latest resolves the most recent read build.
# renovate: datasource=docker depName=ghcr.io/anthony-spruyt/claude-agent-read versioning=semver
FROM ghcr.io/anthony-spruyt/claude-agent-read:1.0.88@sha256:c4081c4dbc12a60c1173695e35bad96e6202cc805e152711eba41b51511d3df6

# Ephemeral agent pod — lifespan managed by n8n spawner
HEALTHCHECK NONE

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

USER root

# libatomic1: pre-commit's nodeenv builds its own node binary (not the
# nodejs.org prebuilt tarball in the read base), and that binary dynamically
# links libatomic.so.1. Without it `pre-commit run` fails at hook-env install
# with "libatomic.so.1: cannot open shared object file". Lives here because
# pre-commit is added in this layer. Ref spruyt-labs#1878.
# Error-Mode=any turns an unreachable mirror into a hard failure instead of a
# warning that resurfaces later as "has no installation candidate"; the outer
# loop rides out the ubuntu.com timeouts that are routine on GitHub runners.
RUN ok=""; \
  for attempt in 1 2 3 4 5; do \
  if apt-get update -o APT::Update::Error-Mode=any; then ok=1; break; fi; \
  echo "apt-get update failed (attempt ${attempt}), retrying"; \
  sleep $((attempt * 10)); \
  done; \
  [[ -n "${ok}" ]] \
  && apt-get install -y --no-install-recommends libatomic1 \
  && rm -rf /var/lib/apt/lists/*

# Go (prebuilt tarball). Root needed to write under /usr/local.
# renovate: depName=golang datasource=docker
ARG GO_VERSION="1.27.0"
RUN ARCH="$(dpkg --print-architecture)" \
  && curl -fsSL --retry 3 --retry-delay 5 "https://go.dev/dl/go${GO_VERSION}.linux-${ARCH}.tar.gz" | tar -C /usr/local -xz
ENV PATH="/usr/local/go/bin:${PATH}"

# pre-commit (installed for the uid 1000 node user, matching the chain).
# pre-commit builds node/python hook environments at runtime; python3 comes
# from apt in the read base, so there is no fragile from-source Python build.
# renovate: depName=pre-commit datasource=pypi
ARG PRECOMMIT_VERSION="4.6.2"
USER 1000
RUN pip install --no-cache-dir --break-system-packages pre-commit=="${PRECOMMIT_VERSION}"

# Working directory
WORKDIR /workspace
