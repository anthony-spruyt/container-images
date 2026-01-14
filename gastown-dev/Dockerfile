FROM mcr.microsoft.com/devcontainers/base:jammy

# Install jq, tmux and feature-install CLI
RUN apt-get update && apt-get install -y --no-install-recommends jq tmux \
    && rm -rf /var/lib/apt/lists/* \
    && curl -fsSL https://raw.githubusercontent.com/MilkClouds/devcontainer-feature-installer/main/install-feature-cli.sh | bash

# Pre-install cosign for Python 3.14+ signature verification
# renovate: datasource=github-releases depName=sigstore/cosign
ARG COSIGN_VERSION="v3.0.4"
RUN ARCH=$(dpkg --print-architecture) \
    && curl -fsSL "https://github.com/sigstore/cosign/releases/download/${COSIGN_VERSION}/cosign_${COSIGN_VERSION#v}_${ARCH}.deb" -o /tmp/cosign.deb \
    && dpkg -i /tmp/cosign.deb \
    && rm /tmp/cosign.deb

# Copy devcontainer.json and install features from it
COPY assets/.devcontainer.json /tmp/devcontainer.json
RUN feature-install --features "$(jq -c '.features' /tmp/devcontainer.json)" \
    && rm /tmp/devcontainer.json

# Copy install scripts
COPY assets/scripts/ /tmp/scripts/
RUN chmod +x /tmp/scripts/*.sh

# Set up PATH for installed features (nvm/node, go, python, py-utils)
ENV NVM_DIR="/usr/local/share/nvm"
ENV PATH="/usr/local/py-utils/bin:/usr/local/share/nvm/current/bin:/usr/local/go/bin:/usr/local/python/current/bin:$PATH"

# Install safe-chain first to protect subsequent npm/pip installs
RUN /tmp/scripts/install-safe-chain.sh

# Run remaining install scripts (safe-chain shims protect npm/pip)
ENV PATH="/root/.safe-chain/shims:$PATH"
RUN for script in /tmp/scripts/install-*.sh; do \
      [ "$(basename "$script")" = "install-safe-chain.sh" ] && continue; \
      echo "Running $script..." && "$script"; \
    done

# Set non-root user (vscode is created by base image)
USER vscode

# Set up user-specific tools for vscode user (runtime)
# safe-chain: Already installed globally, just run setup for this user
RUN safe-chain setup && safe-chain setup-ci
ENV PATH="/home/vscode/.safe-chain/shims:$PATH"

# helm plugins: Install for vscode user
RUN /tmp/scripts/install-helm-plugins.sh

# Clean up install scripts
USER root
RUN rm -rf /tmp/scripts
USER vscode
