#!/bin/bash
set -euo pipefail

IMAGE="${1:?Usage: test.sh <image-ref>}"
DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Testing claude-agent-read image..."

echo "Test 1: claude-plugins-bootstrap matches devcontainer-common's..."
if ! cmp -s "$DIR/assets/claude-plugins-bootstrap.sh" "$DIR/../devcontainer-common/assets/claude-plugins-bootstrap.sh"; then
  echo "  ERROR: claude-agent-read/assets/claude-plugins-bootstrap.sh differs from devcontainer-common's; copy it over" >&2
  exit 1
fi
echo "OK: copy is current"

docker run --rm "$IMAGE" bash -c '
set -euo pipefail

for bin in claude node python3 git npm jq gh rg claude-plugins-bootstrap ap-mcp-headers; do
  if ! command -v "$bin" &>/dev/null; then
    echo "FAIL: $bin not found"
    exit 1
  fi
  echo "OK: $bin found at $(which "$bin")"
done

# Functional checks: exercise the binaries, do not just locate them.
claude --version
node -e "console.log(\"OK: node executes\")"
safe-chain --version
gh --version
rg --version
'

echo "=== Managed settings, MCP header helper and plugin bootstrap ==="
docker run --rm \
  -v "$DIR/test-config.sh:/test-config.sh:ro" \
  "$IMAGE" bash /test-config.sh

echo "All tests passed."
