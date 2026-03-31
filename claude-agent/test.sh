#!/bin/bash
set -euo pipefail

IMAGE="${1:?Usage: test.sh <image-ref>}"

echo "Testing claude-agent image..."

docker run --rm "$IMAGE" bash -c '
set -euo pipefail

for bin in claude node python3 git npm; do
  if ! command -v "$bin" &>/dev/null; then
    echo "FAIL: $bin not found"
    exit 1
  fi
  echo "OK: $bin found at $(which "$bin")"
done

claude --version
safe-chain --version

# Verify MCP config is baked in
if [ ! -f /workspace/.mcp.json ]; then
  echo "FAIL: /workspace/.mcp.json not found"
  exit 1
fi
echo "OK: .mcp.json present"

echo "All tests passed."
'
