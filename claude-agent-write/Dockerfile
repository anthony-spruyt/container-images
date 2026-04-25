FROM node:24-slim@sha256:dad1a61d4421f0e72068d9f864c73c1e2a617e2cdb23edc777dbc6fe2c90e720

# Ephemeral agent pod — lifespan managed by n8n spawner
HEALTHCHECK NONE

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
  ca-certificates curl git openssh-client jq python3 python3-pip \
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
ARG RIPGREP_VERSION="14.1.1"
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
RUN pip install --no-cache-dir --break-system-packages pre-commit=="${PRECOMMIT_VERSION}"
ENV PATH="/home/node/.local/bin:${PATH}"

# Claude Code CLI (native binary — npm datasource tracks versions)
# renovate: depName=@anthropic-ai/claude-code datasource=npm
ARG CLAUDE_VERSION="2.1.109"
RUN curl -fsSL https://claude.ai/install.sh | bash -s -- "$CLAUDE_VERSION"

# Working directory
WORKDIR /workspace
