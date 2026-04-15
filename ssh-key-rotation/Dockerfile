# SSH Key Rotation image for Coder workspace SSH signing/auth key rotation.
# Designed for PSA restricted: non-root (UID 1000), read-only root filesystem,
# all caps dropped. Keypair material written to /tmp (mount as memory emptyDir).
#
# Required env:
#   GITHUB_PAT - GitHub PAT with admin:public_key + admin:ssh_signing_key scopes
#
# Pin to specific digest for supply chain security (renovate updates this)
FROM alpine:3.23@sha256:25109184c71bdad752c8312a8623239686a9a2071e8825f20acb8f2198c3f659

# renovate: datasource=github-releases depName=kubernetes/kubernetes
ARG KUBECTL_VERSION=v1.35.3
ARG KUBECTL_SHA256_AMD64=fd31c7d7129260e608f6faf92d5984c3267ad0b5ead3bced2fe125686e286ad6
ARG KUBECTL_SHA256_ARM64=6f0cd088a82dde5d5807122056069e2fac4ed447cc518efc055547ae46525f14

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
# hadolint ignore=DL4006
RUN ARCH="$(apk --print-arch)" \
    && case "${ARCH}" in \
         x86_64)  KUBE_ARCH=amd64; KUBE_SHA="${KUBECTL_SHA256_AMD64}" ;; \
         aarch64) KUBE_ARCH=arm64; KUBE_SHA="${KUBECTL_SHA256_ARM64}" ;; \
         *) echo "Unsupported arch: ${ARCH}" >&2; exit 1 ;; \
       esac \
    && curl -fsSL -o /usr/local/bin/kubectl \
         "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/${KUBE_ARCH}/kubectl" \
    && echo "${KUBE_SHA}  /usr/local/bin/kubectl" | sha256sum -c - \
    && chmod 0755 /usr/local/bin/kubectl

COPY assets/rotate-ssh-key.sh /usr/local/bin/rotate-ssh-key.sh
RUN chmod 0755 /usr/local/bin/rotate-ssh-key.sh

USER rotator
WORKDIR /home/rotator

ENTRYPOINT ["/usr/local/bin/rotate-ssh-key.sh"]
