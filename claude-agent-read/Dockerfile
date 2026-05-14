FROM node:24-slim@sha256:24dc26ef1e3c3690f27ebc4136c9c186c3133b25563ae4d7f0692e4d1fe5db0e

# Ephemeral agent pod — lifespan managed by n8n spawner
HEALTHCHECK NONE

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
  ca-certificates curl git openssh-client jq python3 python3-pip \
  && rm -rf /var/lib/apt/lists/*

# GitHub CLI
# renovate: depName=cli/cli datasource=github-releases
ARG GH_VERSION="2.92.0"
RUN ARCH="$(dpkg --print-architecture)" \
  && curl -fsSL --retry 3 --retry-delay 5 "https://github.com/cli/cli/releases/download/v${GH_VERSION}/gh_${GH_VERSION}_linux_${ARCH}.deb" -o /tmp/gh.deb \
  && dpkg -i /tmp/gh.deb \
  && rm /tmp/gh.deb

# ripgrep
# renovate: depName=BurntSushi/ripgrep datasource=github-releases
ARG RIPGREP_VERSION="15.1.0"
RUN ARCH="$(dpkg --print-architecture)" \
  && case "${ARCH}" in amd64) RG_ARCH="x86_64-unknown-linux-musl";; arm64) RG_ARCH="aarch64-unknown-linux-gnu";; *) echo "unsupported: ${ARCH}"; exit 1;; esac \
  && curl -fsSL --retry 3 --retry-delay 5 \
    "https://github.com/BurntSushi/ripgrep/releases/download/${RIPGREP_VERSION}/ripgrep-${RIPGREP_VERSION}-${RG_ARCH}.tar.gz" \
  | tar -xz -C /usr/local/bin --strip-components=1 "ripgrep-${RIPGREP_VERSION}-${RG_ARCH}/rg"

# Aikido safe-chain (installed globally, then set up for node user)
# renovate: depName=@aikidosec/safe-chain datasource=npm
ARG SAFE_CHAIN_VERSION="1.5.3"
RUN npm install -g "@aikidosec/safe-chain@${SAFE_CHAIN_VERSION}"

# agentmemory MCP (pre-installed so npx resolves locally without network fetch)
# renovate: depName=@agentmemory/mcp datasource=npm
ARG AGENTMEMORY_VERSION="0.9.12"
RUN npm install -g "@agentmemory/mcp@${AGENTMEMORY_VERSION}"

# Set up safe-chain shims for node user before any npm/pip calls
USER 1000
RUN safe-chain setup && safe-chain setup-ci
ENV PATH="/home/node/.safe-chain/shims:${PATH}"

# Claude Code CLI (native binary — npm datasource tracks versions)
# renovate: depName=@anthropic-ai/claude-code datasource=npm
ARG CLAUDE_VERSION="2.1.141"
RUN curl -fsSL https://claude.ai/install.sh | bash -s -- "$CLAUDE_VERSION"
ENV PATH="/home/node/.local/bin:${PATH}"

# Working directory
WORKDIR /workspace
