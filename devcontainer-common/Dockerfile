FROM mcr.microsoft.com/devcontainers/base:jammy@sha256:0e50c6443341c5302ad4728049013750eb9ca35b1a3cbf003ba5fcbd5e033798

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN printf 'Acquire::Retries "5";\nAcquire::http::Timeout "30";\nAcquire::http::Pipeline-Depth "0";\nAcquire::Retries::Delay::Maximum "10";\n' \
    > /etc/apt/apt.conf.d/80-retries \
    && apt-get update && apt-get install -y --no-install-recommends jq \
    && rm -rf /var/lib/apt/lists/* \
    && curl -fsSL https://raw.githubusercontent.com/MilkClouds/devcontainer-feature-installer/main/install-feature-cli.sh | bash

COPY assets/.devcontainer.json /tmp/devcontainer.json
RUN feature-install --features "$(jq -c '.features' /tmp/devcontainer.json)" \
    && rm /tmp/devcontainer.json

COPY assets/scripts/ /tmp/scripts/

ENV NVM_DIR="/usr/local/share/nvm"
ENV PATH="/usr/local/py-utils/bin:/usr/local/share/nvm/current/bin:/usr/local/python/current/bin:$PATH"

# renovate: datasource=npm depName=@aikidosec/safe-chain
ARG SAFE_CHAIN_VERSION="1.4.9"
RUN chmod +x /tmp/scripts/*.sh \
    && SAFE_CHAIN_VERSION="${SAFE_CHAIN_VERSION}" /tmp/scripts/install-safe-chain.sh

ENV PATH="/root/.safe-chain/shims:$PATH"

# Run remaining install scripts (safe-chain shims protect npm/pip)
RUN for script in /tmp/scripts/install-*.sh; do \
      [ "$(basename "$script")" = "install-safe-chain.sh" ] && continue; \
      echo "Running $script..." && "$script"; \
    done

# renovate: datasource=pypi depName=pre-commit
ARG PRE_COMMIT_VERSION="4.5.1"
# renovate: datasource=pypi depName=pipx
ARG PIPX_VERSION="1.11.1"
RUN export PIPX_HOME="/usr/local/py-utils" \
    && export PIPX_BIN_DIR="/usr/local/py-utils/bin" \
    && mkdir -p "$PIPX_HOME" "$PIPX_BIN_DIR" \
    && pip install --no-cache-dir "pipx==${PIPX_VERSION}" \
    && pipx install "pre-commit==${PRE_COMMIT_VERSION}"

# Policy-enforcing podman wrapper + runtime post-create script
COPY assets/agent-run /usr/local/bin/agent-run
COPY assets/post-create.sh /usr/local/bin/devcontainer-post-create
RUN chmod 755 /usr/local/bin/agent-run /usr/local/bin/devcontainer-post-create \
    && rm -rf /tmp/scripts

HEALTHCHECK NONE

USER vscode

RUN safe-chain setup && safe-chain setup-ci
ENV PATH="/home/vscode/.safe-chain/shims:$PATH"
