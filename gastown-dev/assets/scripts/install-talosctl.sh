#!/bin/bash
set -euo pipefail

# renovate: datasource=github-releases depName=siderolabs/talos
TALOSCTL_VERSION="v1.12.2"

# Remove existing binary to force fresh download (version updates)
rm -f /usr/local/bin/talosctl

# Download from GitHub releases (more reliable than talos.dev/install)
curl -sSfL "https://github.com/siderolabs/talos/releases/download/${TALOSCTL_VERSION}/talosctl-linux-amd64" -o /usr/local/bin/talosctl
chmod +x /usr/local/bin/talosctl

echo "✅ talosctl ${TALOSCTL_VERSION} installed successfully."
