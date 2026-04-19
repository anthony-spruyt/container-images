# coder-gitops: bundles `coder` CLI + `kubectl` for Coder GitOps Jobs
# (template sync + session-token rotation). Designed for PSA restricted:
# non-root (UID 1000), read-only rootfs, all caps dropped.
#
# Pin to specific digest for supply chain security (renovate updates this)
FROM alpine:3.23@sha256:25109184c71bdad752c8312a8623239686a9a2071e8825f20acb8f2198c3f659

# Job/CronJob — runs to completion, no health check applicable
HEALTHCHECK NONE

# renovate: datasource=github-releases depName=coder/coder
ARG CODER_VERSION=v2.31.9

# renovate: datasource=github-releases depName=kubernetes/kubernetes
ARG KUBECTL_VERSION=v1.35.3

RUN apk upgrade --no-cache \
    && apk add --no-cache curl jq ca-certificates tzdata bash \
    && addgroup -g 1000 coder \
    && adduser -D -u 1000 -G coder -h /home/coder coder

# Install kubectl. Checksum fetched from same release server alongside binary.
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

# Install coder CLI from upstream release tarball.
# hadolint ignore=DL4006
RUN ARCH="$(apk --print-arch)" \
    && case "${ARCH}" in \
         x86_64)  CODER_ARCH=amd64 ;; \
         aarch64) CODER_ARCH=arm64 ;; \
         *) echo "Unsupported arch: ${ARCH}" >&2; exit 1 ;; \
       esac \
    && CODER_VER_NUM="${CODER_VERSION#v}" \
    && curl -fsSL -o /tmp/coder.tar.gz \
         "https://github.com/coder/coder/releases/download/${CODER_VERSION}/coder_${CODER_VER_NUM}_linux_${CODER_ARCH}.tar.gz" \
    && tar -xzf /tmp/coder.tar.gz -C /tmp ./coder \
    && mv /tmp/coder /usr/local/bin/coder \
    && chmod 0755 /usr/local/bin/coder \
    && rm -f /tmp/coder.tar.gz

COPY assets/push-templates.sh assets/rotate-token.sh /usr/local/bin/
RUN chmod 0755 /usr/local/bin/push-templates.sh /usr/local/bin/rotate-token.sh

USER coder
WORKDIR /home/coder
