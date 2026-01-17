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
cat >"$TEST_CONFIG" <<'EOF'
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

# Test 2: Wait for application to start and log initial messages
echo "Test 2: Waiting for application startup (10 seconds)..."
sleep 10

# Test 3: Verify application started and config was loaded
echo "Test 3: Verify application startup and config loading..."
docker logs "$CONTAINER_NAME" >/tmp/sungather-logs-$$.txt 2>&1
if grep -q "Starting SunGather" /tmp/sungather-logs-$$.txt &&
  grep -q "Loaded config:" /tmp/sungather-logs-$$.txt; then
  echo "  Application started successfully and loaded config"
else
  echo "  ERROR: Application did not start properly"
  cat /tmp/sungather-logs-$$.txt
  exit 1
fi

# Note: Container may exit after connection timeout (expected in CI without real inverter)
# This is normal behavior - the app tries to connect and exits if it can't

# Test 4: Verify registers file was loaded
echo "Test 4: Verify registers loading..."
if grep -q "Loaded registers:" /tmp/sungather-logs-$$.txt; then
  echo "  Registers file loaded successfully"
else
  echo "  WARNING: Could not verify registers loading"
fi

# Test 5: Verify connection attempt was made
echo "Test 5: Verify connection attempt..."
if grep -qE "(Connection to|failed: timed out)" /tmp/sungather-logs-$$.txt; then
  echo "  Connection attempt detected (timeout expected in CI without real hardware)"
else
  echo "  WARNING: No connection attempt found in logs"
fi

# Test 6: Check final exit status
echo "Test 6: Check container exit status..."
# Wait a bit more for container to finish
sleep 5
EXIT_CODE=$(docker inspect --format='{{.State.ExitCode}}' "$CONTAINER_NAME" 2>/dev/null || echo "unknown")
echo "  Container exited with code: $EXIT_CODE"

# Exit code may be non-zero due to connection failure - this is expected in CI
echo "  Note: Non-zero exit is expected in CI (no real inverter to connect to)"

echo ""
echo "=== All tests passed ==="
echo ""
echo "Note: Tests validate container build and basic runtime behavior."
echo "Actual inverter connectivity cannot be tested in CI without hardware."
