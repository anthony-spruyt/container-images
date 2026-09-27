#!/bin/bash
set -euo pipefail

apt-get remove -y --purge moby-cli moby-engine moby-buildx moby-compose \
  moby-containerd moby-runc docker-ce-cli docker-ce 2>/dev/null || true

apt-get update && apt-get install -y --no-install-recommends podman

rm -rf /var/lib/apt/lists/*

# Subordinate IDs for rootful `--userns=auto` (used by agent-run)
echo "containers:2147483647:2147483648" >>/etc/subuid
echo "containers:2147483647:2147483648" >>/etc/subgid

echo "podman installed"
