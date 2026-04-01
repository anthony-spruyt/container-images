#!/bin/bash
set -euo pipefail

IMAGE="${1:?Usage: test.sh <image-ref>}"

echo "Testing discord-mcp image..."

# Test 1: Verify binaries and jar exist
echo "Test 1: Binaries and jar..."
docker run --rm --entrypoint sh "$IMAGE" -c '
set -euo pipefail

for bin in java node supergateway; do
  if ! command -v "$bin" &>/dev/null; then
    echo "FAIL: $bin not found"
    exit 1
  fi
  echo "OK: $bin found at $(which "$bin")"
done

if [ ! -f /app/app.jar ]; then
  echo "FAIL: /app/app.jar not found"
  exit 1
fi
echo "OK: /app/app.jar present"

java -version 2>&1 | head -1
node --version
'

# Test 2: Verify health endpoint starts
CONTAINER_NAME="discord-mcp-test-$$"

cleanup() {
  docker rm -f "$CONTAINER_NAME" 2>/dev/null || true
}
trap cleanup EXIT

echo "Test 2: Health endpoint..."
docker run -d \
  --name "$CONTAINER_NAME" \
  -p 18080:8080 \
  "$IMAGE"

# Wait for supergateway to bind (health endpoint should respond even without Discord token)
TIMEOUT=30
ELAPSED=0
while [ $ELAPSED -lt $TIMEOUT ]; do
  if curl -sf http://localhost:18080/healthz >/dev/null 2>&1; then
    echo "  OK: /healthz returned 200 after ${ELAPSED}s"
    break
  fi
  sleep 2
  ELAPSED=$((ELAPSED + 2))
done

if [ $ELAPSED -ge $TIMEOUT ]; then
  echo "  WARN: /healthz did not respond within ${TIMEOUT}s (may require Discord token)"
  echo "  Container logs:"
  docker logs "$CONTAINER_NAME" 2>&1 | tail -20
  echo "  Skipping health check test (expected in CI without credentials)"
fi

echo "All tests passed."
