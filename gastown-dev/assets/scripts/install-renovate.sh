#!/bin/bash
set -euo pipefail

# renovate: depName=renovate datasource=npm
VERSION="42.74.2"

echo "Installing renovate@${VERSION}..."
npm install -g "renovate@${VERSION}"

echo "✅ renovate ${VERSION} installed successfully."
