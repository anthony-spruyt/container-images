#!/bin/bash
# Test script for llm-guard container
# Usage: ./test.sh <image-ref>

set -euo pipefail

IMAGE_REF="${1:?Usage: $0 <image-ref>}"
CONTAINER_NAME="llm-guard-test-$$"

cleanup() {
  echo "Cleaning up..."
  docker rm -f "$CONTAINER_NAME" 2>/dev/null || true
}
trap cleanup EXIT

echo "=== LLM Guard Container Tests ==="
echo "Image: $IMAGE_REF"
echo ""

# Test 1: Container starts with minimal scanner config (avoids loading all default scanners)
echo "Test 1: Container startup..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
docker run -d \
  --name "$CONTAINER_NAME" \
  -p 8000:8000 \
  -v "${SCRIPT_DIR}/assets/test-scanners.yml:/home/user/app/config/scanners.yml:ro" \
  -e LOG_LEVEL=INFO \
  -e LOG_JSON=true \
  -e APP_PORT=8000 \
  "$IMAGE_REF"

# Test 2: Wait for healthz
echo "Test 2: Waiting for /healthz (max 60s)..."
TIMEOUT=60
ELAPSED=0
while [ $ELAPSED -lt $TIMEOUT ]; do
  if curl -sf http://localhost:8000/healthz >/dev/null 2>&1; then
    echo "  Healthy after ${ELAPSED}s"
    break
  fi
  sleep 5
  ELAPSED=$((ELAPSED + 5))
done

if [ $ELAPSED -ge $TIMEOUT ]; then
  echo "  ERROR: Timeout waiting for /healthz"
  docker logs "$CONTAINER_NAME"
  exit 1
fi

# Test 3: Verify /readyz
echo "Test 3: Readiness check..."
if curl -sf http://localhost:8000/readyz >/dev/null 2>&1; then
  echo "  /readyz OK"
else
  echo "  ERROR: /readyz failed"
  docker logs "$CONTAINER_NAME"
  exit 1
fi

echo ""
echo "=== All tests passed ==="
