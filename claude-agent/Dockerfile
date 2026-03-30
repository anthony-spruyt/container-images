FROM node:20-slim

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl git jq python3 python3-pip \
    && rm -rf /var/lib/apt/lists/*

# kubectl (for bootstrap only — removed by entrypoint before agent starts)
# renovate: depName=kubernetes/kubernetes datasource=github-releases
ARG KUBECTL_VERSION="v1.33.0"
RUN curl -fsSL "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/amd64/kubectl" \
      -o /usr/local/bin/kubectl \
    && chmod +x /usr/local/bin/kubectl

# Aikido safe-chain
# renovate: depName=@aikidosec/safe-chain datasource=npm
ARG SAFE_CHAIN_VERSION="1.4.4"
RUN npm install -g "@aikidosec/safe-chain@${SAFE_CHAIN_VERSION}" \
    && safe-chain setup && safe-chain setup-ci
ENV PATH="/root/.safe-chain/shims:${PATH}"

# Claude Code CLI (native installer)
RUN curl -fsSL https://claude.ai/install.sh | bash
ENV PATH="/root/.claude/bin:${PATH}"

# Working directory
WORKDIR /workspace

# Entrypoint
COPY assets/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
