#!/bin/bash
set -euo pipefail

IMAGE="${1:?Usage: test.sh <image-ref>}"

echo "Testing claude-agent image..."

docker run --rm --entrypoint="" "$IMAGE" bash -c '
set -euo pipefail

for bin in claude node python3 git npm kubectl; do
  if ! command -v "$bin" &>/dev/null; then
    echo "FAIL: $bin not found"
    exit 1
  fi
  echo "OK: $bin found at $(which "$bin")"
done

claude --version
safe-chain --version

echo "All tests passed."
'
