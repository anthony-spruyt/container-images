#!/bin/bash
set -euo pipefail

# renovate: depName=renovate datasource=npm
VERSION="42.85.7"

echo "Installing renovate@${VERSION}..."
npm install -g --safe-chain-skip-minimum-package-age "renovate@${VERSION}"

echo "✅ renovate ${VERSION} installed successfully."
