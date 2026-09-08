#!/bin/bash
# Test script for chrony container
# Usage: ./test.sh <image-ref>

set -euo pipefail

IMAGE_REF="${1:?Usage: $0 <image-ref>}"
CONTAINER_NAME="chrony-test-$$"
CONTAINER_NAME_ZEROCAP="chrony-test-zerocap-$$"
CONTAINER_NAME_NTS="chrony-test-nts-$$"
TEST_PORT=11123

cleanup() {
  echo "Cleaning up..."
  docker rm -f "$CONTAINER_NAME" "$CONTAINER_NAME_ZEROCAP" "$CONTAINER_NAME_NTS" 2>/dev/null || true
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

# Test 3: Verify chronyc can query tracking info (proves chronyd is running)
echo "Test 3: Verify chronyc tracking..."
if docker exec "$CONTAINER_NAME" chronyc -h /var/lib/chrony/chrony.sock -n tracking >/dev/null 2>&1; then
  echo "  chronyc tracking successful"
  docker exec "$CONTAINER_NAME" chronyc -h /var/lib/chrony/chrony.sock -n tracking | head -5
else
  echo "  ERROR: chronyc tracking failed"
  docker logs "$CONTAINER_NAME"
  exit 1
fi

# Test 4: Verify chrony is tracking sources
echo "Test 4: Verify NTP source activity..."
if docker exec "$CONTAINER_NAME" chronyc -h /var/lib/chrony/chrony.sock -n activity | grep -q "sources"; then
  echo "  chrony is active and tracking sources"
else
  echo "  WARNING: Could not verify source activity"
fi

# Test 5: Verify the packaged chrony version is recorded in the image
echo "Test 5: Upstream chrony version recorded..."
UPSTREAM_VERSION=$(docker exec "$CONTAINER_NAME" cat /etc/chrony-upstream-version 2>/dev/null || true)
if [[ -n "$UPSTREAM_VERSION" ]]; then
  echo "  Packaged chrony: $UPSTREAM_VERSION"
else
  echo "  ERROR: /etc/chrony-upstream-version is missing or empty" >&2
  exit 1
fi

# Test 6: Verify chronyd is built with NTS support
echo "Test 6: chronyd built with NTS..."
CHRONYD_FLAGS=$(docker run --rm --entrypoint chronyd "$IMAGE_REF" --version 2>&1 || true)
echo "  $CHRONYD_FLAGS"
if grep -q '+NTS' <<<"$CHRONYD_FLAGS"; then
  echo "  chronyd reports +NTS"
else
  echo "  ERROR: chronyd built without NTS support (expected +NTS)" >&2
  echo "  Alpine splits NTS into the chrony-nts package - check the Dockerfile apk add" >&2
  exit 1
fi

# Test 7: Verify the container actually stays up with ENABLE_NTS=true
echo "Test 7: ENABLE_NTS=true startup..."
docker run -d \
  --name "$CONTAINER_NAME_NTS" \
  -e NTP_SERVERS="time.cloudflare.com" \
  -e ENABLE_NTS="true" \
  "$IMAGE_REF"

ELAPSED=0
while [[ $ELAPSED -lt $TIMEOUT ]]; do
  STATUS=$(docker inspect --format='{{.State.Health.Status}}' "$CONTAINER_NAME_NTS" 2>/dev/null || echo "starting")
  case "$STATUS" in
  healthy)
    echo "  NTS container is healthy after ${ELAPSED}s"
    break
    ;;
  unhealthy)
    echo "  ERROR: NTS container became unhealthy" >&2
    docker logs "$CONTAINER_NAME_NTS" >&2
    exit 1
    ;;
  *)
    sleep 2
    ELAPSED=$((ELAPSED + 2))
    ;;
  esac
done

if [[ $ELAPSED -ge $TIMEOUT ]]; then
  echo "  ERROR: Timeout waiting for NTS container to become healthy" >&2
  docker logs "$CONTAINER_NAME_NTS" >&2
  exit 1
fi

# chronyd exits quietly on "Missing NTS support", so assert it is still running
if [[ "$(docker inspect --format='{{.State.Running}}' "$CONTAINER_NAME_NTS")" != "true" ]]; then
  echo "  ERROR: NTS container is not running" >&2
  docker logs "$CONTAINER_NAME_NTS" >&2
  exit 1
fi

if docker logs "$CONTAINER_NAME_NTS" 2>&1 | grep -qi "Missing NTS support"; then
  echo "  ERROR: chronyd reported 'Missing NTS support'" >&2
  docker logs "$CONTAINER_NAME_NTS" >&2
  exit 1
fi
echo "  ENABLE_NTS=true starts and stays healthy"

# Test 8: Verify zero-capability mode works (--cap-drop=ALL)
echo "Test 8: Zero-capability mode (--cap-drop=ALL)..."
docker run -d \
  --name "$CONTAINER_NAME_ZEROCAP" \
  --cap-drop=ALL \
  -e NTP_SERVERS="time.cloudflare.com" \
  "$IMAGE_REF"

# Wait for zero-cap container to be healthy
ELAPSED=0
while [ $ELAPSED -lt $TIMEOUT ]; do
  STATUS=$(docker inspect --format='{{.State.Health.Status}}' "$CONTAINER_NAME_ZEROCAP" 2>/dev/null || echo "starting")
  case "$STATUS" in
  healthy)
    echo "  Zero-cap container is healthy after ${ELAPSED}s"
    break
    ;;
  unhealthy)
    echo "  ERROR: Zero-cap container became unhealthy"
    docker logs "$CONTAINER_NAME_ZEROCAP"
    exit 1
    ;;
  *)
    sleep 2
    ELAPSED=$((ELAPSED + 2))
    ;;
  esac
done

if [ $ELAPSED -ge $TIMEOUT ]; then
  echo "  ERROR: Timeout waiting for zero-cap container"
  docker logs "$CONTAINER_NAME_ZEROCAP"
  exit 1
fi

# Verify chronyc works in zero-cap mode
if docker exec "$CONTAINER_NAME_ZEROCAP" chronyc -h /var/lib/chrony/chrony.sock -n tracking >/dev/null 2>&1; then
  echo "  chronyc tracking works in zero-cap mode"
else
  echo "  ERROR: chronyc failed in zero-cap mode"
  docker logs "$CONTAINER_NAME_ZEROCAP"
  exit 1
fi

echo ""
echo "=== All tests passed ==="
