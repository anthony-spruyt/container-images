FROM node:24-slim@sha256:03eae3ef7e88a9de535496fb488d67e02b9d96a063a8967bae657744ecd513f2

# Ephemeral agent pod — lifespan managed by n8n spawner
HEALTHCHECK NONE

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
  ca-certificates curl git openssh-client jq python3 python3-pip \
  && rm -rf /var/lib/apt/lists/*

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

# kubectl
# renovate: depName=kubernetes/kubernetes datasource=github-releases
ARG KUBECTL_VERSION="v1.35.4"
RUN ARCH="$(dpkg --print-architecture)" \
  && curl -fsSL --retry 3 --retry-delay 5 "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/${ARCH}/kubectl" -o /usr/local/bin/kubectl \
  && chmod +x /usr/local/bin/kubectl

# kustomize
# renovate: depName=kubernetes-sigs/kustomize datasource=github-releases versioning=regex:^kustomize/v(?<major>\d+)\.(?<minor>\d+)\.(?<patch>\d+)$
ARG KUSTOMIZE_VERSION="v5.8.0"
RUN ARCH="$(dpkg --print-architecture)" \
  && curl -fsSL --retry 3 --retry-delay 5 "https://github.com/kubernetes-sigs/kustomize/releases/download/kustomize%2F${KUSTOMIZE_VERSION}/kustomize_${KUSTOMIZE_VERSION}_linux_${ARCH}.tar.gz" \
  | tar -xz -C /usr/local/bin

# helm
# renovate: depName=helm/helm datasource=github-releases
ARG HELM_VERSION="v4.1.4"
RUN ARCH="$(dpkg --print-architecture)" \
  && curl -fsSL --retry 3 --retry-delay 5 "https://get.helm.sh/helm-${HELM_VERSION}-linux-${ARCH}.tar.gz" \
  | tar -xz -C /tmp \
  && mv "/tmp/linux-${ARCH}/helm" /usr/local/bin/helm \
  && rm -rf /tmp/linux-*

# helmfile
# renovate: depName=helmfile/helmfile datasource=github-releases
ARG HELMFILE_VERSION="v1.4.4"
RUN ARCH="$(dpkg --print-architecture)" \
  && HELMFILE_VERSION_NUM="${HELMFILE_VERSION#v}" \
  && curl -fsSL --retry 3 --retry-delay 5 "https://github.com/helmfile/helmfile/releases/download/${HELMFILE_VERSION}/helmfile_${HELMFILE_VERSION_NUM}_linux_${ARCH}.tar.gz" \
  | tar -xz -C /usr/local/bin helmfile

# cilium
# renovate: depName=cilium/cilium-cli datasource=github-releases
ARG CILIUM_VERSION="v0.19.2"
RUN ARCH="$(dpkg --print-architecture)" \
  && curl -fsSL --retry 3 --retry-delay 5 "https://github.com/cilium/cilium-cli/releases/download/${CILIUM_VERSION}/cilium-linux-${ARCH}.tar.gz" \
  | tar -xz -C /usr/local/bin

# hubble
# renovate: depName=cilium/hubble datasource=github-releases
ARG HUBBLE_VERSION="v1.18.6"
RUN ARCH="$(dpkg --print-architecture)" \
  && curl -fsSL --retry 3 --retry-delay 5 "https://github.com/cilium/hubble/releases/download/${HUBBLE_VERSION}/hubble-linux-${ARCH}.tar.gz" \
  | tar -xz -C /usr/local/bin

# talosctl
# renovate: depName=siderolabs/talos datasource=github-releases
ARG TALOSCTL_VERSION="v1.10.3"
RUN ARCH="$(dpkg --print-architecture)" \
  && curl -fsSL --retry 3 --retry-delay 5 "https://github.com/siderolabs/talos/releases/download/${TALOSCTL_VERSION}/talosctl-linux-${ARCH}" -o /usr/local/bin/talosctl \
  && chmod +x /usr/local/bin/talosctl

# flux
# renovate: depName=fluxcd/flux2 datasource=github-releases
ARG FLUX_VERSION="v2.6.1"
RUN ARCH="$(dpkg --print-architecture)" \
  && curl -fsSL --retry 3 --retry-delay 5 "https://github.com/fluxcd/flux2/releases/download/${FLUX_VERSION}/flux_${FLUX_VERSION#v}_linux_${ARCH}.tar.gz" \
  | tar -xz -C /usr/local/bin

# velero
# renovate: depName=vmware-tanzu/velero datasource=github-releases
ARG VELERO_VERSION="v1.18.0"
RUN ARCH="$(dpkg --print-architecture)" \
  && curl -fsSL --retry 3 --retry-delay 5 "https://github.com/vmware-tanzu/velero/releases/download/${VELERO_VERSION}/velero-${VELERO_VERSION}-linux-${ARCH}.tar.gz" \
  | tar -xz -C /tmp \
  && mv "/tmp/velero-${VELERO_VERSION}-linux-${ARCH}/velero" /usr/local/bin/velero \
  && rm -rf /tmp/velero-*

# cnpg kubectl plugin
# renovate: depName=cloudnative-pg/cloudnative-pg datasource=github-releases
ARG CNPG_VERSION="v1.29.0"
RUN ARCH="$(uname -m)" \
  && CNPG_VERSION_NUM="${CNPG_VERSION#v}" \
  && curl -fsSL --retry 3 --retry-delay 5 "https://github.com/cloudnative-pg/cloudnative-pg/releases/download/${CNPG_VERSION}/kubectl-cnpg_${CNPG_VERSION_NUM}_linux_${ARCH}.tar.gz" \
  | tar -xz -C /usr/local/bin kubectl-cnpg

# falcoctl
# renovate: depName=falcosecurity/falcoctl datasource=github-releases
ARG FALCOCTL_VERSION="v0.12.2"
RUN ARCH="$(dpkg --print-architecture)" \
  && FALCOCTL_VERSION_NUM="${FALCOCTL_VERSION#v}" \
  && curl -fsSL --retry 3 --retry-delay 5 "https://github.com/falcosecurity/falcoctl/releases/download/${FALCOCTL_VERSION}/falcoctl_${FALCOCTL_VERSION_NUM}_linux_${ARCH}.tar.gz" \
  | tar -xz -C /usr/local/bin falcoctl

# Aikido safe-chain (installed globally, then set up for node user)
# renovate: depName=@aikidosec/safe-chain datasource=npm
ARG SAFE_CHAIN_VERSION="1.5.0"
RUN npm install -g "@aikidosec/safe-chain@${SAFE_CHAIN_VERSION}"

# Set up safe-chain shims for node user before any npm/pip calls
USER 1000
RUN safe-chain setup && safe-chain setup-ci
ENV PATH="/home/node/.safe-chain/shims:${PATH}"

# Claude Code CLI (native binary — npm datasource tracks versions)
# renovate: depName=@anthropic-ai/claude-code datasource=npm
ARG CLAUDE_VERSION="2.1.109"
RUN curl -fsSL https://claude.ai/install.sh | bash -s -- "$CLAUDE_VERSION"
ENV PATH="/home/node/.local/bin:${PATH}"

# Helm plugins (installed as node user — helm stores plugins in $HOME)
# renovate: depName=databus23/helm-diff datasource=github-releases
ARG HELM_DIFF_VERSION="v3.15.6"
RUN helm plugin install https://github.com/databus23/helm-diff --verify=false --version "${HELM_DIFF_VERSION}"

# renovate: depName=knechtionscoding/helm-schema-gen datasource=github-releases
ARG HELM_SCHEMA_GEN_VERSION="0.0.10"
RUN helm plugin install https://github.com/knechtionscoding/helm-schema-gen --verify=false --version "${HELM_SCHEMA_GEN_VERSION}"

# Working directory
WORKDIR /workspace
