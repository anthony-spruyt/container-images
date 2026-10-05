FROM mcr.microsoft.com/devcontainers/base:resolute@sha256:edfb983aab9c579a385dc23c57d7d3703f5ec920124d99c16204a2cac465aab4

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN printf 'Acquire::Retries "5";\nAcquire::http::Timeout "30";\nAcquire::http::Pipeline-Depth "0";\nAcquire::Retries::Delay::Maximum "10";\n' \
    > /etc/apt/apt.conf.d/80-retries \
    && apt-get update && apt-get install -y --no-install-recommends bats bats-assert bats-support jq \
    && rm -rf /var/lib/apt/lists/* \
    && curl -fsSL https://raw.githubusercontent.com/MilkClouds/devcontainer-feature-installer/main/install-feature-cli.sh | bash

COPY assets/.devcontainer.json /tmp/devcontainer.json
RUN sed '/^\s*\/\//d' /tmp/devcontainer.json | jq -c '.features' > /tmp/features.json \
    && feature-install --features "$(cat /tmp/features.json)" \
    && rm -rf /tmp/* /tmp/.[!.]*

COPY assets/scripts/ /tmp/scripts/

ENV NVM_DIR="/usr/local/share/nvm"
ENV PATH="/usr/local/py-utils/bin:/usr/local/share/nvm/current/bin:/usr/local/python/current/bin:$PATH"

RUN chmod +x /tmp/scripts/*.sh \
    && for script in /tmp/scripts/install-*.sh; do \
         echo "Running $script..." && "$script"; \
       done

# renovate: datasource=pypi depName=pre-commit
ARG PRE_COMMIT_VERSION="4.6.2"
# renovate: datasource=pypi depName=pipx
ARG PIPX_VERSION="1.17.7"
RUN export PIPX_HOME="/usr/local/py-utils" \
    && export PIPX_BIN_DIR="/usr/local/py-utils/bin" \
    && mkdir -p "$PIPX_HOME" "$PIPX_BIN_DIR" \
    && pip install --no-cache-dir "pipx==${PIPX_VERSION}" \
    && pipx install "pre-commit==${PRE_COMMIT_VERSION}"

# renovate: datasource=pypi depName=mdformat
ARG MDFORMAT_VERSION="1.0.0"
# renovate: datasource=pypi depName=mdformat-gfm
ARG MDFORMAT_GFM_VERSION="1.0.0"
# renovate: datasource=pypi depName=mdformat-frontmatter
ARG MDFORMAT_FRONTMATTER_VERSION="2.1.2"
# renovate: datasource=pypi depName=mdformat-admon
ARG MDFORMAT_ADMON_VERSION="2.1.1"
RUN pip install --no-cache-dir \
    "mdformat==${MDFORMAT_VERSION}" \
    "mdformat-gfm==${MDFORMAT_GFM_VERSION}" \
    "mdformat-frontmatter==${MDFORMAT_FRONTMATTER_VERSION}" \
    "mdformat-admon==${MDFORMAT_ADMON_VERSION}"

COPY assets/podman /usr/local/bin/podman
COPY assets/agent-run /usr/local/bin/agent-run
COPY assets/post-create.sh /usr/local/bin/devcontainer-post-create
COPY assets/podman-config.sh /usr/local/bin/devcontainer-podman-config
COPY assets/nexus-config.sh /usr/local/bin/devcontainer-nexus-config
RUN chmod 755 /usr/local/bin/podman /usr/local/bin/agent-run /usr/local/bin/devcontainer-post-create \
      /usr/local/bin/devcontainer-podman-config /usr/local/bin/devcontainer-nexus-config \
    && ln -s podman /usr/local/bin/docker \
    && rm -rf /tmp/* /tmp/.[!.]*

HEALTHCHECK NONE
