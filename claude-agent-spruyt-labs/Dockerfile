# claude-agent-spruyt-labs = claude-agent-write + Kubernetes/GitOps SRE tooling.
# Pinned to a digest by Renovate once claude-agent-write publishes; until then
# :latest resolves the most recent write build.
# renovate: datasource=docker depName=ghcr.io/anthony-spruyt/claude-agent-write versioning=semver
FROM ghcr.io/anthony-spruyt/claude-agent-write:1.0.50@sha256:112fddedee122533070ad3ef1a29e3344045f772a9a95250887c0434d03c91e7

# Ephemeral agent pod — lifespan managed by n8n spawner
HEALTHCHECK NONE

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# SRE binaries install under /usr/local/bin — needs root.
USER root

# kubectl
# renovate: depName=kubernetes/kubernetes datasource=github-releases
ARG KUBECTL_VERSION="v1.36.1"
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
ARG HELM_VERSION="v4.2.0"
RUN ARCH="$(dpkg --print-architecture)" \
  && curl -fsSL --retry 3 --retry-delay 5 "https://get.helm.sh/helm-${HELM_VERSION}-linux-${ARCH}.tar.gz" \
  | tar -xz -C /tmp \
  && mv "/tmp/linux-${ARCH}/helm" /usr/local/bin/helm \
  && rm -rf /tmp/linux-*

# helmfile
# renovate: depName=helmfile/helmfile datasource=github-releases
ARG HELMFILE_VERSION="v1.5.2"
RUN ARCH="$(dpkg --print-architecture)" \
  && HELMFILE_VERSION_NUM="${HELMFILE_VERSION#v}" \
  && curl -fsSL --retry 3 --retry-delay 5 "https://github.com/helmfile/helmfile/releases/download/${HELMFILE_VERSION}/helmfile_${HELMFILE_VERSION_NUM}_linux_${ARCH}.tar.gz" \
  | tar -xz -C /usr/local/bin helmfile

# cilium
# renovate: depName=cilium/cilium-cli datasource=github-releases
ARG CILIUM_VERSION="v0.19.4"
RUN ARCH="$(dpkg --print-architecture)" \
  && curl -fsSL --retry 3 --retry-delay 5 "https://github.com/cilium/cilium-cli/releases/download/${CILIUM_VERSION}/cilium-linux-${ARCH}.tar.gz" \
  | tar -xz -C /usr/local/bin

# talosctl
# renovate: depName=siderolabs/talos datasource=github-releases
ARG TALOSCTL_VERSION="v1.13.3"
RUN ARCH="$(dpkg --print-architecture)" \
  && curl -fsSL --retry 3 --retry-delay 5 "https://github.com/siderolabs/talos/releases/download/${TALOSCTL_VERSION}/talosctl-linux-${ARCH}" -o /usr/local/bin/talosctl \
  && chmod +x /usr/local/bin/talosctl

# flux
# renovate: depName=fluxcd/flux2 datasource=github-releases
ARG FLUX_VERSION="v2.8.8"
RUN ARCH="$(dpkg --print-architecture)" \
  && curl -fsSL --retry 3 --retry-delay 5 "https://github.com/fluxcd/flux2/releases/download/${FLUX_VERSION}/flux_${FLUX_VERSION#v}_linux_${ARCH}.tar.gz" \
  | tar -xz -C /usr/local/bin

# velero
# renovate: depName=vmware-tanzu/velero datasource=github-releases
ARG VELERO_VERSION="v1.18.1"
RUN ARCH="$(dpkg --print-architecture)" \
  && curl -fsSL --retry 3 --retry-delay 5 "https://github.com/vmware-tanzu/velero/releases/download/${VELERO_VERSION}/velero-${VELERO_VERSION}-linux-${ARCH}.tar.gz" \
  | tar -xz -C /tmp \
  && mv "/tmp/velero-${VELERO_VERSION}-linux-${ARCH}/velero" /usr/local/bin/velero \
  && rm -rf /tmp/velero-*

# cnpg kubectl plugin
# renovate: depName=cloudnative-pg/cloudnative-pg datasource=github-releases
ARG CNPG_VERSION="v1.29.1"
RUN ARCH="$(uname -m)" \
  && CNPG_VERSION_NUM="${CNPG_VERSION#v}" \
  && curl -fsSL --retry 3 --retry-delay 5 "https://github.com/cloudnative-pg/cloudnative-pg/releases/download/${CNPG_VERSION}/kubectl-cnpg_${CNPG_VERSION_NUM}_linux_${ARCH}.tar.gz" \
  | tar -xz -C /usr/local/bin kubectl-cnpg

# falcoctl
# renovate: depName=falcosecurity/falcoctl datasource=github-releases
ARG FALCOCTL_VERSION="v0.13.0"
RUN ARCH="$(dpkg --print-architecture)" \
  && FALCOCTL_VERSION_NUM="${FALCOCTL_VERSION#v}" \
  && curl -fsSL --retry 3 --retry-delay 5 "https://github.com/falcosecurity/falcoctl/releases/download/${FALCOCTL_VERSION}/falcoctl_${FALCOCTL_VERSION_NUM}_linux_${ARCH}.tar.gz" \
  | tar -xz -C /usr/local/bin falcoctl

# Helm plugins install into $HOME — run as the uid 1000 node user.
USER 1000

# renovate: depName=databus23/helm-diff datasource=github-releases
ARG HELM_DIFF_VERSION="v3.15.7"
RUN helm plugin install https://github.com/databus23/helm-diff --verify=false --version "${HELM_DIFF_VERSION}"

# renovate: depName=knechtionscoding/helm-schema-gen datasource=github-releases
ARG HELM_SCHEMA_GEN_VERSION="0.0.10"
RUN helm plugin install https://github.com/knechtionscoding/helm-schema-gen --verify=false --version "${HELM_SCHEMA_GEN_VERSION}"

# Working directory
WORKDIR /workspace
