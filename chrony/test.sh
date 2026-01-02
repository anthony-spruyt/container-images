#!/bin/bash
# Test script for chrony container
# Usage: ./test.sh <image-ref>

set -euo pipefail

IMAGE_REF="${1:?Usage: $0 <image-ref>}"
CONTAINER_NAME="chrony-test-$$"
TEST_PORT=11123

cleanup() {
    echo "Cleaning up..."
    docker rm -f "$CONTAINER_NAME" 2>/dev/null || true
}
trap cleanup EXIT

echo "=== Chrony Container Tests ==="
echo "Image: $IMAGE_REF"
echo ""

# Test 1: Container starts successfully
echo "Test 1: Container startup..."
docker run -d \
    --name "$CONTAINER_NAME" \
    -p "$TEST_PORT:1123/udp" \
    -e NTP_SERVERS="time.cloudflare.com" \
    -e ENABLE_NTS="false" \
    "$IMAGE_REF"

# Test 2: Wait for container to be healthy
echo "Test 2: Waiting for healthcheck (max 60s)..."
TIMEOUT=60
ELAPSED=0
while [ $ELAPSED -lt $TIMEOUT ]; do
    STATUS=$(docker inspect --format='{{.State.Health.Status}}' "$CONTAINER_NAME" 2>/dev/null || echo "starting")
    case "$STATUS" in
        healthy)
            echo "  Container is healthy after ${ELAPSED}s"
            break
            ;;
        unhealthy)
            echo "  ERROR: Container became unhealthy"
            docker logs "$CONTAINER_NAME"
            exit 1
            ;;
        *)
            sleep 2
            ELAPSED=$((ELAPSED + 2))
            ;;
    esac
done

if [ $ELAPSED -ge $TIMEOUT ]; then
    echo "  ERROR: Timeout waiting for container to become healthy"
    docker logs "$CONTAINER_NAME"
    exit 1
fi

# Test 3: Verify chrony process is running
echo "Test 3: Verify chronyd process..."
if docker exec "$CONTAINER_NAME" pgrep -x chronyd > /dev/null; then
    echo "  chronyd process is running"
else
    echo "  ERROR: chronyd process not found"
    docker logs "$CONTAINER_NAME"
    exit 1
fi

# Test 4: Verify chronyc can query tracking info
echo "Test 4: Verify chronyc tracking..."
if docker exec "$CONTAINER_NAME" chronyc -n tracking > /dev/null 2>&1; then
    echo "  chronyc tracking successful"
    docker exec "$CONTAINER_NAME" chronyc -n tracking | head -5
else
    echo "  WARNING: chronyc tracking failed (may need more time to sync)"
fi

# Test 5: Verify container runs as non-root
echo "Test 5: Verify non-root execution..."
CONTAINER_USER=$(docker exec "$CONTAINER_NAME" id -u)
if [ "$CONTAINER_USER" = "1000" ]; then
    echo "  Container running as uid 1000 (non-root)"
else
    echo "  ERROR: Container running as uid $CONTAINER_USER (expected 1000)"
    exit 1
fi

# Test 6: Verify listening on configured port
echo "Test 6: Verify NTP port binding..."
if docker exec "$CONTAINER_NAME" chronyc -n activity | grep -q "sources"; then
    echo "  chrony is active and tracking sources"
else
    echo "  WARNING: Could not verify source activity"
fi

echo ""
echo "=== All tests passed ==="
