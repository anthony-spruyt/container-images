#!/bin/bash
# Test coder-gitops image: required tooling, non-root user, scripts present,
# read-only rootfs compatible.
# Usage: ./test.sh <image-ref>

set -euo pipefail

IMAGE_REF="${1:?Usage: $0 <image-ref>}"

echo "=== coder-gitops image tests ==="
echo "Image: $IMAGE_REF"

# Test 1: required binaries present
echo "Test 1: required binaries..."
for bin in coder kubectl curl jq bash; do
  if ! docker run --rm --entrypoint sh "$IMAGE_REF" -c "command -v $bin >/dev/null"; then
    echo "  ERROR: missing binary: $bin"
    exit 1
  fi
  echo "  found: $bin"
done

# Test 2: runs as non-root UID 1000
echo "Test 2: non-root user..."
UID_OUT=$(docker run --rm --entrypoint id "$IMAGE_REF" -u)
if [ "$UID_OUT" != "1000" ]; then
  echo "  ERROR: expected UID 1000, got $UID_OUT"
  exit 1
fi
echo "  UID=1000 ok"

# Test 3: scripts present and executable
echo "Test 3: scripts..."
for script in push-templates.sh rotate-token.sh; do
  if ! docker run --rm --entrypoint sh "$IMAGE_REF" -c "test -x /usr/local/bin/$script"; then
    echo "  ERROR: /usr/local/bin/$script missing or not executable"
    exit 1
  fi
  echo "  found: $script"
done

# Test 4: script syntax valid
echo "Test 4: script syntax check..."
for script in push-templates.sh rotate-token.sh; do
  if ! docker run --rm --entrypoint bash "$IMAGE_REF" -n "/usr/local/bin/$script"; then
    echo "  ERROR: $script has syntax errors"
    exit 1
  fi
done
echo "  syntax ok"

# Test 5: kubectl + coder run (--client / --version)
echo "Test 5: kubectl + coder version..."
docker run --rm --entrypoint kubectl "$IMAGE_REF" version --client >/dev/null
docker run --rm --entrypoint coder "$IMAGE_REF" version >/dev/null
echo "  versions ok"

# Test 6: read-only root filesystem compatible (PSA restricted)
echo "Test 6: read-only rootfs + tmpfs /tmp..."
if ! docker run --rm \
  --read-only \
  --tmpfs /tmp:rw,size=16m \
  --entrypoint sh "$IMAGE_REF" \
  -c "kubectl version --client >/dev/null && coder version >/dev/null"; then
  echo "  ERROR: binaries failed under read-only rootfs"
  exit 1
fi
echo "  read-only rootfs ok"

echo ""
echo "=== All tests passed ==="
