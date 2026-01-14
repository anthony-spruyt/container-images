#!/bin/bash
set -euo pipefail

# renovate: depName=mikefarah/yq datasource=github-releases
VERSION="v4.50.1"

ARCH=$(uname -m)
case "$ARCH" in
  x86_64) ARCH="amd64" ;;
  aarch64) ARCH="arm64" ;;
  *) echo "Unsupported architecture: $ARCH"; exit 1 ;;
esac

# Remove existing to ensure version update
if [[ -f /usr/local/bin/yq ]]; then
  rm -f /usr/local/bin/yq
fi

BINARY="yq_linux_${ARCH}"
curl -Lo /usr/local/bin/yq "https://github.com/mikefarah/yq/releases/download/${VERSION}/${BINARY}"
chmod +x /usr/local/bin/yq

echo "✅ yq ${VERSION} installed successfully."
