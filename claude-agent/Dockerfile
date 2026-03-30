FROM node:20-slim

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl git jq python3 python3-pip \
    && rm -rf /var/lib/apt/lists/*

# kubectl (for bootstrap only — removed by entrypoint before agent starts)
# Install to user-writable path so non-root entrypoint can rm it
# renovate: depName=kubernetes/kubernetes datasource=github-releases
ARG KUBECTL_VERSION="v1.33.0"
RUN curl -fsSL "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/amd64/kubectl" \
      -o /usr/local/bin/kubectl \
    && chmod +x /usr/local/bin/kubectl

# Aikido safe-chain (installed globally, then set up for node user)
# renovate: depName=@aikidosec/safe-chain datasource=npm
ARG SAFE_CHAIN_VERSION="1.4.4"
RUN npm install -g "@aikidosec/safe-chain@${SAFE_CHAIN_VERSION}"

# Claude Code CLI (native installer — install as node user)
USER node
RUN safe-chain setup && safe-chain setup-ci \
    && curl -fsSL https://claude.ai/install.sh | bash
ENV PATH="/home/node/.safe-chain/shims:/home/node/.claude/bin:${PATH}"

# Working directory (node user owns it)
WORKDIR /workspace
RUN mkdir -p /home/node/.claude

# Entrypoint
USER root
COPY assets/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

USER node
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
