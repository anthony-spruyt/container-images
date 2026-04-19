FROM mcr.microsoft.com/devcontainers/base:jammy@sha256:0e50c6443341c5302ad4728049013750eb9ca35b1a3cbf003ba5fcbd5e033798

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN apt-get update && apt-get install -y --no-install-recommends jq \
    && rm -rf /var/lib/apt/lists/* \
    && curl -fsSL https://raw.githubusercontent.com/MilkClouds/devcontainer-feature-installer/main/install-feature-cli.sh | bash

COPY assets/.devcontainer.json /tmp/devcontainer.json
RUN feature-install --features "$(jq -c '.features' /tmp/devcontainer.json)" \
    && rm /tmp/devcontainer.json

ENV NVM_DIR="/usr/local/share/nvm"
ENV PATH="/usr/local/py-utils/bin:/usr/local/share/nvm/current/bin:/usr/local/python/current/bin:$PATH"

# renovate: datasource=pypi depName=pre-commit
ARG PRE_COMMIT_VERSION="4.5.1"
RUN export PIPX_HOME="/usr/local/py-utils" \
    && export PIPX_BIN_DIR="/usr/local/py-utils/bin" \
    && mkdir -p "$PIPX_HOME" "$PIPX_BIN_DIR" \
    && pip install --no-cache-dir pipx \
    && pipx install "pre-commit==${PRE_COMMIT_VERSION}"

HEALTHCHECK NONE

USER vscode
