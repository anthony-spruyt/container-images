#!/bin/bash
set -euo pipefail

BIN_PATH="/usr/local/bin/capacitor-next"
TMP_PATH="/tmp/capacitor-next"

echo "🚀 Downloading Capacitor binary..."
curl -L "https://github.com/gimlet-io/capacitor/releases/download/capacitor-next/next-$(uname)-$(uname -m)" \
  -o "$TMP_PATH"

chmod +x "$TMP_PATH"
mv "$TMP_PATH" "$BIN_PATH"

echo "✅ Installed to $BIN_PATH"
