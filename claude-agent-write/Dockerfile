# renovate: depName=python datasource=docker
FROM python:3.13-slim-bookworm@sha256:bb73517d48bd32016e15eade0c009b2724ec3a025a9975b5cd9b251d0dcadb33 AS python

FROM node:24-slim@sha256:dad1a61d4421f0e72068d9f864c73c1e2a617e2cdb23edc777dbc6fe2c90e720

# Ephemeral agent pod — lifespan managed by n8n spawner
HEALTHCHECK NONE

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Python 3.13 from official image (mdformat requires 3.13+ for exclude config)
COPY --from=python /usr/local/bin/python3* /usr/local/bin/
COPY --from=python /usr/local/bin/pip* /usr/local/bin/
COPY --from=python /usr/local/lib/python3.13 /usr/local/lib/python3.13
COPY --from=python /usr/local/lib/libpython3.13.so* /usr/local/lib/
RUN ldconfig && ln -sf /usr/local/bin/python3.13 /usr/local/bin/python3

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
  ca-certificates curl git openssh-client jq libatomic1 \
  && rm -rf /var/lib/apt/lists/*

# GitHub CLI
# renovate: depName=cli/cli datasource=github-releases
ARG GH_VERSION="2.73.0"
RUN ARCH="$(dpkg --print-architecture)" \
  && curl -fsSL "https://github.com/cli/cli/releases/download/v${GH_VERSION}/gh_${GH_VERSION}_linux_${ARCH}.deb" -o /tmp/gh.deb \
  && dpkg -i /tmp/gh.deb \
  && rm /tmp/gh.deb

# ripgrep
# renovate: depName=BurntSushi/ripgrep datasource=github-releases
ARG RIPGREP_VERSION="15.1.0"
RUN ARCH="$(dpkg --print-architecture)" \
  && curl -fsSL "https://github.com/BurntSushi/ripgrep/releases/download/${RIPGREP_VERSION}/ripgrep_${RIPGREP_VERSION}-1_${ARCH}.deb" -o /tmp/rg.deb \
  && dpkg -i /tmp/rg.deb \
  && rm /tmp/rg.deb

# Go
# renovate: depName=golang datasource=docker
ARG GO_VERSION="1.24.4"
RUN ARCH="$(dpkg --print-architecture)" \
  && curl -fsSL "https://go.dev/dl/go${GO_VERSION}.linux-${ARCH}.tar.gz" | tar -C /usr/local -xz
ENV PATH="/usr/local/go/bin:${PATH}"

# Aikido safe-chain (installed globally, then set up for node user)
# renovate: depName=@aikidosec/safe-chain datasource=npm
ARG SAFE_CHAIN_VERSION="1.4.9"
RUN npm install -g "@aikidosec/safe-chain@${SAFE_CHAIN_VERSION}"

# Set up safe-chain shims for node user before any npm/pip calls
USER 1000
RUN safe-chain setup && safe-chain setup-ci
ENV PATH="/home/node/.safe-chain/shims:${PATH}"

# pre-commit
# renovate: depName=pre-commit datasource=pypi
ARG PRECOMMIT_VERSION="4.6.0"
RUN pip install --no-cache-dir pre-commit=="${PRECOMMIT_VERSION}"
ENV PATH="/home/node/.local/bin:${PATH}"

# Claude Code CLI (native binary — npm datasource tracks versions)
# renovate: depName=@anthropic-ai/claude-code datasource=npm
ARG CLAUDE_VERSION="2.1.109"
RUN curl -fsSL https://claude.ai/install.sh | bash -s -- "$CLAUDE_VERSION"

# Working directory
WORKDIR /workspace
