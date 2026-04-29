# renovate: depName=ubuntu datasource=docker versioning=ubuntu
FROM ubuntu:jammy@sha256:962f6cadeae0ea6284001009daa4cc9a8c37e75d1f5191cf0eb83fe565b63dd7

# Ephemeral agent pod — lifespan managed by n8n spawner
HEALTHCHECK NONE

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# System deps (persist) + Python build deps (purged after compile)
RUN apt-get update && apt-get install -y --no-install-recommends \
  ca-certificates curl git openssh-client jq libatomic1 xz-utils \
  libsqlite3-0 libreadline8 libncurses6 libffi8 liblzma5 libbz2-1.0 libssl3 \
  && apt-get install -y --no-install-recommends \
  build-essential pkg-config libssl-dev zlib1g-dev libbz2-dev libreadline-dev \
  libsqlite3-dev libncurses-dev libffi-dev liblzma-dev \
  && rm -rf /var/lib/apt/lists/*

# Python (built from source — Renovate tracks via github-releases)
# renovate: depName=python/cpython datasource=github-releases extractVersion=^v(?<version>.+)$
ARG PYTHON_VERSION="3.13.13"
RUN curl -fsSL --retry 3 --retry-delay 5 "https://www.python.org/ftp/python/${PYTHON_VERSION}/Python-${PYTHON_VERSION}.tgz" \
  | tar -xz -C /tmp
WORKDIR /tmp/Python-${PYTHON_VERSION}
RUN ./configure --prefix=/usr/local --enable-optimizations --with-ensurepip=install 2>&1 | tail -5 \
  && make -j"$(nproc)" 2>&1 | tail -5 \
  && make install \
  && ln -sf /usr/local/bin/python3 /usr/local/bin/python \
  && ln -sf /usr/local/bin/pip3 /usr/local/bin/pip
WORKDIR /

# Remove Python build artifacts and deps
RUN rm -rf /tmp/Python-* \
  && apt-get purge -y \
    build-essential pkg-config libssl-dev zlib1g-dev libbz2-dev libreadline-dev \
    libsqlite3-dev libncurses-dev libffi-dev liblzma-dev \
  && apt-get autoremove -y \
  && rm -rf /var/lib/apt/lists/*

# Node.js (prebuilt binary tarball — Renovate tracks via node-version datasource)
# renovate: depName=node datasource=node versioning=node
ARG NODE_VERSION="24.15.0"
RUN ARCH="$(dpkg --print-architecture)" \
  && case "${ARCH}" in amd64) ARCH=x64;; arm64) ARCH=arm64;; *) echo "unsupported: ${ARCH}"; exit 1;; esac \
  && curl -fsSL --retry 3 --retry-delay 5 "https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-${ARCH}.tar.xz" \
  | tar -xJ --strip-components=1 -C /usr/local

# GitHub CLI
# renovate: depName=cli/cli datasource=github-releases
ARG GH_VERSION="2.91.0"
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

# Go
# renovate: depName=golang datasource=docker
ARG GO_VERSION="1.26.1"
RUN ARCH="$(dpkg --print-architecture)" \
  && curl -fsSL --retry 3 --retry-delay 5 "https://go.dev/dl/go${GO_VERSION}.linux-${ARCH}.tar.gz" | tar -C /usr/local -xz
ENV PATH="/usr/local/go/bin:${PATH}"

# Aikido safe-chain (installed globally, then set up for node user)
# renovate: depName=@aikidosec/safe-chain datasource=npm
ARG SAFE_CHAIN_VERSION="1.5.0"
RUN npm install -g "@aikidosec/safe-chain@${SAFE_CHAIN_VERSION}" \
  && useradd -m -u 1000 -s /bin/bash node
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
