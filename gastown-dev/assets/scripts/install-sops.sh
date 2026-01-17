#!/bin/bash
set -euo pipefail

# renovate: depName=getsops/sops datasource=github-releases
VERSION="v3.11.0"

ARCH=$(uname -m)
case "$ARCH" in
x86_64) ARCH="amd64" ;;
aarch64) ARCH="arm64" ;;
*)
    echo "Unsupported architecture: $ARCH"
    exit 1
    ;;
esac

# Remove existing to ensure version update
if [[ -f /usr/local/bin/sops ]]; then
    rm -f /usr/local/bin/sops
fi

BINARY="sops-${VERSION}.linux.${ARCH}"
curl -Lo /usr/local/bin/sops "https://github.com/getsops/sops/releases/download/${VERSION}/${BINARY}"
chmod +x /usr/local/bin/sops

echo "✅ sops ${VERSION} installed successfully."
