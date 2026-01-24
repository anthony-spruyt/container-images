#!/bin/bash
set -euo pipefail

# renovate: depName=FiloSottile/age datasource=github-releases
VERSION="v1.3.1"

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
rm -f /usr/local/bin/age /usr/local/bin/age-keygen

# Download and extract age
TARBALL="age-${VERSION}-linux-${ARCH}.tar.gz"
curl -fsSLo /tmp/age.tar.gz "https://github.com/FiloSottile/age/releases/download/${VERSION}/${TARBALL}"
tar -xzf /tmp/age.tar.gz -C /tmp
mv /tmp/age/age /usr/local/bin/age
mv /tmp/age/age-keygen /usr/local/bin/age-keygen
chmod +x /usr/local/bin/age /usr/local/bin/age-keygen
rm -rf /tmp/age.tar.gz /tmp/age

echo "✅ age ${VERSION} installed successfully."
age --version
