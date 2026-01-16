#!/bin/bash
set -euo pipefail

# renovate: depName=fluxcd/flux2 datasource=github-releases
VERSION="v2.7.5"

ARCH=$(uname -m)
case "$ARCH" in
  x86_64) ARCH="amd64" ;;
  aarch64) ARCH="arm64" ;;
  *) echo "Unsupported architecture: $ARCH"; exit 1 ;;
esac

# Remove existing to ensure version update
if [[ -f /usr/local/bin/flux ]]; then
  rm -f /usr/local/bin/flux
fi

TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

TARBALL="flux_${VERSION#v}_linux_${ARCH}.tar.gz"
curl -Lo "$TMPDIR/$TARBALL" "https://github.com/fluxcd/flux2/releases/download/${VERSION}/${TARBALL}"
curl -Lo "$TMPDIR/${TARBALL}.sha256" "https://github.com/fluxcd/flux2/releases/download/${VERSION}/flux_${VERSION#v}_checksums.txt"
(cd "$TMPDIR" && grep "$TARBALL" "${TARBALL}.sha256" | sha256sum --check)
tar -xzf "$TMPDIR/$TARBALL" -C "$TMPDIR"
mv "$TMPDIR/flux" /usr/local/bin/flux
chmod +x /usr/local/bin/flux

echo "✅ Flux CLI ${VERSION} installed successfully."
