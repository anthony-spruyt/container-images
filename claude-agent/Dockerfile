FROM node:24-slim@sha256:b506e7321f176aae77317f99d67a24b272c1f09f1d10f1761f2773447d8da26c

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
  ca-certificates curl git jq python3 python3-pip \
  && rm -rf /var/lib/apt/lists/*

# Aikido safe-chain (installed globally, then set up for node user)
# renovate: depName=@aikidosec/safe-chain datasource=npm
ARG SAFE_CHAIN_VERSION="1.4.9"
RUN npm install -g "@aikidosec/safe-chain@${SAFE_CHAIN_VERSION}"

# Set up safe-chain shims for node user before any npm/pip calls
USER 1000
RUN safe-chain setup && safe-chain setup-ci
ENV PATH="/home/node/.safe-chain/shims:${PATH}"

# Claude Code CLI (native binary — npm datasource tracks versions)
# renovate: depName=@anthropic-ai/claude-code datasource=npm
ARG CLAUDE_VERSION="2.1.109"
RUN curl -fsSL https://claude.ai/install.sh | bash -s -- "$CLAUDE_VERSION"
ENV PATH="/home/node/.local/bin:${PATH}"

# Working directory
WORKDIR /workspace
