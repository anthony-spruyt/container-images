#!/bin/bash
# Test ssh-key-rotation image: verify required tooling, non-root user,
# script presence, and PSA-restricted compatibility (read-only rootfs).
# Usage: ./test.sh <image-ref>

set -euo pipefail

IMAGE_REF="${1:?Usage: $0 <image-ref>}"

echo "=== ssh-key-rotation image tests ==="
echo "Image: $IMAGE_REF"

# Test 1: required binaries present
echo "Test 1: required binaries..."
for bin in ssh-keygen curl jq kubectl; do
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

# Test 3: entrypoint script present and executable
echo "Test 3: entrypoint script..."
if ! docker run --rm --entrypoint sh "$IMAGE_REF" -c "test -x /usr/local/bin/rotate-ssh-key.sh"; then
  echo "  ERROR: /usr/local/bin/rotate-ssh-key.sh missing or not executable"
  exit 1
fi
echo "  entrypoint ok"

# Test 4: script syntax valid
echo "Test 4: script syntax check..."
if ! docker run --rm --entrypoint sh "$IMAGE_REF" -c "sh -n /usr/local/bin/rotate-ssh-key.sh"; then
  echo "  ERROR: script has syntax errors"
  exit 1
fi
echo "  syntax ok"

# Test 5: kubectl runs (--client to avoid needing a cluster)
echo "Test 5: kubectl client..."
if ! docker run --rm --entrypoint kubectl "$IMAGE_REF" version --client >/dev/null; then
  echo "  ERROR: kubectl --client failed"
  exit 1
fi
echo "  kubectl ok"

# Test 6: read-only root filesystem compatible (PSA restricted)
echo "Test 6: read-only rootfs + tmpfs /tmp..."
if ! docker run --rm \
  --read-only \
  --tmpfs /tmp:rw,size=64m \
  --entrypoint sh "$IMAGE_REF" \
  -c "ssh-keygen -t ed25519 -f /tmp/id_ed25519 -N '' -C 'test' >/dev/null && test -f /tmp/id_ed25519.pub"; then
  echo "  ERROR: keygen failed under read-only rootfs"
  exit 1
fi
echo "  read-only rootfs ok"

# Test 7: fails fast when required env vars are missing
echo "Test 7: env var validation..."
OUTPUT=$(docker run --rm \
  --read-only \
  --tmpfs /tmp:rw,size=64m \
  "$IMAGE_REF" 2>&1 || true)
if ! echo "$OUTPUT" | grep -q "ERROR:.*is required"; then
  echo "  ERROR: script did not fail for missing env vars"
  exit 1
fi
echo "  env var validation ok"

# Test 8: fails when FORCE_SYNC_NAMESPACES set without FORCE_SYNC_ES_NAME
echo "Test 8: FORCE_SYNC_ES_NAME required with FORCE_SYNC_NAMESPACES..."
OUTPUT=$(docker run --rm \
  --read-only \
  --tmpfs /tmp:rw,size=64m \
  -e GITHUB_PAT=fake \
  -e TITLE_PREFIX=test \
  -e SECRET_NAME=test \
  -e SECRET_NAMESPACE=test \
  -e FORCE_SYNC_NAMESPACES=ns1 \
  "$IMAGE_REF" 2>&1 || true)
if ! echo "$OUTPUT" | grep -q "FORCE_SYNC_ES_NAME is required"; then
  echo "  ERROR: script did not fail for missing FORCE_SYNC_ES_NAME"
  exit 1
fi
echo "  conditional validation ok"

echo ""
echo "=== All tests passed ==="
