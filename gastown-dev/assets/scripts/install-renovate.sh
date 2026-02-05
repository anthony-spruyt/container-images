#!/bin/bash
set -euo pipefail

# renovate: depName=renovate datasource=npm
VERSION="43.3.6"

echo "Installing renovate@${VERSION}..."
npm install -g --safe-chain-skip-minimum-package-age "renovate@${VERSION}"

echo "✅ renovate ${VERSION} installed successfully."
