FROM mcr.microsoft.com/devcontainers/base:jammy

# Install jq, tmux and feature-install CLI
RUN apt-get update && apt-get install -y --no-install-recommends jq tmux \
    && rm -rf /var/lib/apt/lists/* \
    && curl -fsSL https://raw.githubusercontent.com/MilkClouds/devcontainer-feature-installer/main/install-feature-cli.sh | bash

# Copy devcontainer.json and install features from it
COPY assets/devcontainer.json /tmp/devcontainer.json
RUN feature-install --features "$(jq -c '.features' /tmp/devcontainer.json)" \
    && rm /tmp/devcontainer.json

# Copy install scripts
COPY assets/scripts/ /tmp/scripts/
RUN chmod +x /tmp/scripts/*.sh

# Set up PATH for installed features (nvm/node, go, python)
ENV NVM_DIR="/usr/local/share/nvm"
ENV PATH="/usr/local/share/nvm/current/bin:/usr/local/go/bin:/usr/local/python/current/bin:$PATH"

# Install safe-chain first to protect subsequent npm/pip installs
RUN /tmp/scripts/install-safe-chain.sh

# Run remaining install scripts (safe-chain shims protect npm/pip)
ENV PATH="/root/.safe-chain/shims:$PATH"
RUN for script in /tmp/scripts/install-*.sh; do \
      [ "$(basename "$script")" = "install-safe-chain.sh" ] && continue; \
      echo "Running $script..." && "$script"; \
    done \
    && rm -rf /tmp/scripts

# Set non-root user (vscode is created by base image)
USER vscode
