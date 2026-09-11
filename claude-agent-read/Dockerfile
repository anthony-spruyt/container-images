# renovate: depName=ubuntu datasource=docker versioning=ubuntu
FROM ubuntu:resolute@sha256:513c074113a871b51a8d16ab445c88779d6452d937a164fb5cc479f32668a41d

# Ephemeral agent pod — lifespan managed by n8n spawner
HEALTHCHECK NONE

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# System deps. xz-utils is required to extract the node .tar.xz tarball below
# (node:24-slim provided it implicitly; ubuntu minimal does not).
# archive.ubuntu.com times out intermittently on GitHub runners. Without
# Error-Mode=any, apt-get update only warns on an unreachable mirror and the
# install fails later with a confusing "has no installation candidate".
RUN { echo 'Acquire::Retries "5";'; \
  echo 'Acquire::http::Timeout "30";'; \
  echo 'Acquire::http::Pipeline-Depth "0";'; \
  echo 'Acquire::Retries::Delay::Maximum "10";'; \
  } > /etc/apt/apt.conf.d/80-retries; \
  ok=""; \
  for attempt in 1 2 3 4 5; do \
  if apt-get update -o APT::Update::Error-Mode=any; then ok=1; break; fi; \
  echo "apt-get update failed (attempt ${attempt}), retrying"; \
  sleep $((attempt * 10)); \
  done; \
  [[ -n "${ok}" ]] \
  && apt-get install -y --no-install-recommends \
  ca-certificates curl git jq openssh-client python3 python3-pip \
  xz-utils \
  && rm -rf /var/lib/apt/lists/*

# Node.js (prebuilt binary tarball — Renovate tracks via node-version datasource)
# renovate: depName=node datasource=node versioning=node
ARG NODE_VERSION="24.20.0"
RUN ARCH="$(dpkg --print-architecture)" \
  && case "${ARCH}" in amd64) ARCH=x64;; arm64) ARCH=arm64;; *) echo "unsupported: ${ARCH}"; exit 1;; esac \
  && TARBALL="node-v${NODE_VERSION}-linux-${ARCH}.tar.xz" \
  && curl -fsSL --retry 3 --retry-delay 5 "https://nodejs.org/dist/v${NODE_VERSION}/${TARBALL}" -o "/tmp/${TARBALL}" \
  && EXPECTED="$(curl -fsSL --retry 3 --retry-delay 5 "https://nodejs.org/dist/v${NODE_VERSION}/SHASUMS256.txt" | awk -v f="${TARBALL}" '$2 == f {print $1}')" \
  && echo "${EXPECTED}  /tmp/${TARBALL}" | sha256sum -c - \
  && tar -xJ --strip-components=1 -C /usr/local -f "/tmp/${TARBALL}" \
  && rm -f "/tmp/${TARBALL}"

# GitHub CLI
# renovate: depName=cli/cli datasource=github-releases
ARG GH_VERSION="2.100.0"
RUN ARCH="$(dpkg --print-architecture)" \
  && curl -fsSL --retry 3 --retry-delay 5 "https://github.com/cli/cli/releases/download/v${GH_VERSION}/gh_${GH_VERSION}_linux_${ARCH}.deb" -o /tmp/gh.deb \
  && dpkg -i /tmp/gh.deb \
  && rm /tmp/gh.deb

# ripgrep
# renovate: depName=BurntSushi/ripgrep datasource=github-releases
ARG RIPGREP_VERSION="15.2.0"
RUN ARCH="$(dpkg --print-architecture)" \
  && case "${ARCH}" in amd64) RG_ARCH="x86_64-unknown-linux-musl";; arm64) RG_ARCH="aarch64-unknown-linux-gnu";; *) echo "unsupported: ${ARCH}"; exit 1;; esac \
  && curl -fsSL --retry 3 --retry-delay 5 \
    "https://github.com/BurntSushi/ripgrep/releases/download/${RIPGREP_VERSION}/ripgrep-${RIPGREP_VERSION}-${RG_ARCH}.tar.gz" \
  | tar -xz -C /usr/local/bin --strip-components=1 "ripgrep-${RIPGREP_VERSION}-${RG_ARCH}/rg"

# Aikido safe-chain (installed globally, then set up for node user).
# ubuntu has no uid 1000 user; create one named "node" to match downstream
# images and the n8n spawner's expected runtime user.
# renovate: depName=@aikidosec/safe-chain datasource=npm
ARG SAFE_CHAIN_VERSION="1.5.16"
RUN npm install -g "@aikidosec/safe-chain@${SAFE_CHAIN_VERSION}" \
  && if getent passwd 1000 >/dev/null; then userdel -r "$(getent passwd 1000 | cut -d: -f1)"; fi \
  && useradd -m -u 1000 -s /bin/bash node

# Set up safe-chain shims for node user before any npm/pip calls
USER 1000
RUN safe-chain setup && safe-chain setup-ci
ENV PATH="/home/node/.safe-chain/shims:${PATH}"

# Claude Code CLI (native binary — npm datasource tracks versions)
# renovate: depName=@anthropic-ai/claude-code datasource=npm
ARG CLAUDE_VERSION="2.1.268"
RUN curl -fsSL https://claude.ai/install.sh | bash -s -- "$CLAUDE_VERSION"
ENV PATH="/home/node/.local/bin:${PATH}"

# Working directory
WORKDIR /workspace
