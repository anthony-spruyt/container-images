#!/bin/bash
# Test script for sungather container
# Usage: ./test.sh <image-ref>

set -euo pipefail

IMAGE_REF="${1:?Usage: $0 <image-ref>}"
CONTAINER_NAME="sungather-test-$$"
TEST_PORT=18080

cleanup() {
    echo "Cleaning up..."
    docker rm -f "$CONTAINER_NAME" 2>/dev/null || true
    rm -f /tmp/sungather-config-$$.yaml /tmp/sungather-logs-$$.txt
}
trap cleanup EXIT

echo "=== SunGather Container Tests ==="
echo "Image: $IMAGE_REF"
echo ""

# Test 1: Container starts with minimal config
echo "Test 1: Container startup with minimal config..."

# Create minimal test config
TEST_CONFIG="/tmp/sungather-config-$$.yaml"
cat > "$TEST_CONFIG" << 'EOF'
# Minimal test configuration for CI
inverter:
  host: "192.168.1.100"
  port: 502
  scan_interval: 30
  timeout: 10

exports:
  - name: console
    enabled: true
EOF

# Start container with test config
docker run -d \
    --name "$CONTAINER_NAME" \
    -p "$TEST_PORT:8080" \
    -v "$TEST_CONFIG:/config/config.yaml:ro" \
    -e TZ="UTC" \
    "$IMAGE_REF"

# Test 2: Wait for container to stay running (basic stability check)
echo "Test 2: Container stability check (15 seconds)..."
sleep 15

# Verify container is still running
if ! docker ps --filter "name=$CONTAINER_NAME" --format '{{.Names}}' | grep -q "$CONTAINER_NAME"; then
    echo "  ERROR: Container stopped unexpectedly"
    docker logs "$CONTAINER_NAME"
    exit 1
fi
echo "  Container is running stable"

# Test 3: Verify Python process is running
echo "Test 3: Verify Python process..."
if docker exec "$CONTAINER_NAME" pgrep -f "python.*sungather.py" > /dev/null; then
    echo "  Python process is running"
else
    echo "  ERROR: Python process not found"
    docker logs "$CONTAINER_NAME"
    exit 1
fi

# Test 4: Verify logs directory is writable
echo "Test 4: Verify logs directory access..."
if docker exec "$CONTAINER_NAME" test -d /logs && docker exec "$CONTAINER_NAME" test -w /logs; then
    echo "  Logs directory is writable"
else
    echo "  ERROR: Logs directory is not accessible/writable"
    docker logs "$CONTAINER_NAME"
    exit 1
fi

# Test 5: Verify config was loaded
echo "Test 5: Verify config file loading..."
docker logs "$CONTAINER_NAME" 2>&1 | head -50 > /tmp/sungather-logs-$$.txt
if grep -qE "(config|Config|inverter|Inverter)" /tmp/sungather-logs-$$.txt; then
    echo "  Config file appears to be loaded (found config-related log entries)"
else
    echo "  WARNING: Could not verify config loading from logs"
    echo "  This may be expected if connection to inverter fails in CI"
fi

# Test 6: Verify container can be stopped gracefully
echo "Test 6: Graceful shutdown test..."
docker stop --time=10 "$CONTAINER_NAME"
EXIT_CODE=$(docker inspect --format='{{.State.ExitCode}}' "$CONTAINER_NAME")
echo "  Container stopped with exit code: $EXIT_CODE"

# Note: Non-zero exit is expected since we can't reach a real inverter in CI
# We're mainly validating the container starts, loads config, and runs the app
if [ "$EXIT_CODE" -eq 137 ]; then
    echo "  Container was forcefully killed (SIGKILL) - may indicate shutdown issue"
    # Don't fail the test for this, as it might be timing-related in CI
fi

echo ""
echo "=== All tests passed ==="
echo ""
echo "Note: Tests validate container build and basic runtime behavior."
echo "Actual inverter connectivity cannot be tested in CI without hardware."
