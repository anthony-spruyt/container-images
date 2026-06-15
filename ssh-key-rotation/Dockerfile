# SSH Key Rotation — rotates SSH auth + signing keys for any GitHub user account.
# Designed for PSA restricted: non-root (UID 1000), read-only root filesystem,
# all caps dropped. Keypair material written to /tmp (mount as memory emptyDir).
#
# Required env:
#   GITHUB_PAT       — PAT with admin:public_key + admin:ssh_signing_key scopes
#   TITLE_PREFIX     — GitHub key title prefix (e.g. "coder-workspace")
#   SECRET_NAME      — Kubernetes secret to patch
#   SECRET_NAMESPACE — Namespace of that secret
# Optional env:
#   FORCE_SYNC_NAMESPACES — comma-separated namespaces for ExternalSecret force-sync
#   FORCE_SYNC_ES_NAME    — ExternalSecret name to sync
#
# Pin to specific digest for supply chain security (renovate updates this)
FROM alpine:3.24@sha256:a2d49ea686c2adfe3c992e47dc3b5e7fa6e6b5055609400dc2acaeb241c829f4

# CronJob — runs to completion, no health check applicable
HEALTHCHECK NONE

# renovate: datasource=github-releases depName=kubernetes/kubernetes
ARG KUBECTL_VERSION=v1.36.1

# Install runtime dependencies (no runtime apk add - PSA restricted compatible).
# openssh-keygen: ed25519 keypair generation
# curl: GitHub API calls
# jq: parse GitHub API responses
# ca-certificates: TLS to api.github.com / kube-apiserver
# tzdata: consistent timestamp formatting in DATE_SUFFIX
RUN apk upgrade --no-cache \
    && apk add --no-cache openssh-keygen curl jq ca-certificates tzdata \
    && addgroup -g 1000 rotator \
    && adduser -D -u 1000 -G rotator -h /home/rotator rotator

# Install kubectl (not in Alpine main repos at pinned versions).
# Checksum fetched from same release server alongside binary.
# hadolint ignore=DL4006
RUN ARCH="$(apk --print-arch)" \
    && case "${ARCH}" in \
         x86_64)  KUBE_ARCH=amd64 ;; \
         aarch64) KUBE_ARCH=arm64 ;; \
         *) echo "Unsupported arch: ${ARCH}" >&2; exit 1 ;; \
       esac \
    && KUBE_URL="https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/${KUBE_ARCH}/kubectl" \
    && curl -fsSL -o /usr/local/bin/kubectl "${KUBE_URL}" \
    && KUBE_SHA="$(curl -fsSL "${KUBE_URL}.sha256")" \
    && echo "${KUBE_SHA}  /usr/local/bin/kubectl" | sha256sum -c - \
    && chmod 0755 /usr/local/bin/kubectl

COPY assets/rotate-ssh-key.sh /usr/local/bin/rotate-ssh-key.sh
RUN chmod 0755 /usr/local/bin/rotate-ssh-key.sh

USER rotator
WORKDIR /home/rotator

ENTRYPOINT ["/usr/local/bin/rotate-ssh-key.sh"]
