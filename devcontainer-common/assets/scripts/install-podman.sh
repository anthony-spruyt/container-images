#!/bin/bash
set -euo pipefail

apt-get remove -y --purge moby-cli moby-engine moby-buildx moby-compose \
  moby-containerd moby-runc docker-ce-cli docker-ce 2>/dev/null || true

apt-get update && apt-get install -y --no-install-recommends \
  podman \
  podman-docker \
  fuse-overlayfs \
  uidmap \
  slirp4netns

rm -rf /var/lib/apt/lists/*

mkdir -p /etc/containers
touch /etc/containers/nodocker

echo "vscode:100000:65536" >>/etc/subuid
echo "vscode:100000:65536" >>/etc/subgid

echo "podman installed with rootless support"
