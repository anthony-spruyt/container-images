#!/bin/bash
set -euo pipefail

IMAGE="${1:?Usage: test.sh <image-ref>}"

echo "Testing claude-agent-write image..."

docker run --rm "$IMAGE" bash -c '
set -euo pipefail

for bin in claude node python3 git npm jq gh rg go pre-commit; do
  if ! command -v "$bin" &>/dev/null; then
    echo "FAIL: $bin not found"
    exit 1
  fi
  echo "OK: $bin found at $(which "$bin")"
done

claude --version
safe-chain --version
gh --version
rg --version
go version
pre-commit --version

echo "All tests passed."
'
