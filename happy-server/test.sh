#!/bin/bash
# Test happy-server image: non-root user, PSA-restricted run (read-only rootfs),
# migrations, health endpoint, bundled webapp, and state surviving a restart.
# Usage: ./test.sh <image-ref>

set -euo pipefail

IMAGE_REF="${1:?Usage: $0 <image-ref>}"
NAME="happy-server-test-$$"
DATA_VOL="happy-server-test-data-$$"

cleanup() {
  docker rm -f "$NAME" >/dev/null 2>&1 || true
  docker volume rm -f "$DATA_VOL" >/dev/null 2>&1 || true
}
trap cleanup EXIT

start_server() {
  docker run -d --name "$NAME" \
    --read-only \
    --tmpfs /tmp:rw,size=64m \
    --cap-drop ALL \
    --security-opt no-new-privileges \
    -v "$DATA_VOL:/data" \
    -e HANDY_MASTER_SECRET=test-secret \
    "$IMAGE_REF" >/dev/null
}

in_container_get() {
  local path="$1"
  docker exec "$NAME" curl -fsS "http://127.0.0.1:3005${path}"
}

wait_healthy() {
  for _ in $(seq 60); do
    if in_container_get /health >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  echo "  ERROR: /health did not answer within 60s" >&2
  docker logs "$NAME" 2>&1 | tail -n 50
  return 1
}

echo "=== happy-server image tests ==="
echo "Image: $IMAGE_REF"

echo "Test 1: non-root user..."
UID_OUT=$(docker run --rm --entrypoint id "$IMAGE_REF" -u)
if [[ "$UID_OUT" != "1000" ]]; then
  echo "  ERROR: expected UID 1000, got $UID_OUT" >&2
  exit 1
fi
echo "  UID=1000 ok"

echo "Test 2: happy-server on PATH..."
if ! docker run --rm --entrypoint sh "$IMAGE_REF" -c "command -v happy-server >/dev/null"; then
  echo "  ERROR: happy-server not on PATH" >&2
  exit 1
fi
echo "  happy-server ok"

echo "Test 3: fails fast without HANDY_MASTER_SECRET..."
OUTPUT=$(docker run --rm --read-only --tmpfs /tmp:rw,size=64m --tmpfs /data:rw,size=64m,mode=1777 \
  "$IMAGE_REF" 2>&1 || true)
if ! grep -q "HANDY_MASTER_SECRET is required" <<<"$OUTPUT"; then
  echo "  ERROR: server did not reject a missing master secret" >&2
  echo "$OUTPUT" | tail -n 20
  exit 1
fi
echo "  master secret check ok"

echo "Test 4: starts on read-only rootfs and answers /health..."
docker volume create "$DATA_VOL" >/dev/null
# Named volumes are created root-owned; hand /data to the image user like fsGroup would.
docker run --rm --user 0 --entrypoint chown -v "$DATA_VOL:/data" "$IMAGE_REF" 1000:1000 /data
start_server
wait_healthy
echo "  health ok"

echo "Test 5: migrations applied to /data/pglite..."
if ! grep -q "Applied [0-9]* migration" <<<"$(docker logs "$NAME" 2>&1)"; then
  echo "  ERROR: no migrations applied on first start" >&2
  docker logs "$NAME" 2>&1 | tail -n 30
  exit 1
fi
if ! docker exec "$NAME" test -d /data/pglite; then
  echo "  ERROR: /data/pglite missing" >&2
  exit 1
fi
echo "  migrations ok"

echo "Test 6: bundled webapp served at /..."
if ! grep -qi "<html" <<<"$(in_container_get /)"; then
  echo "  ERROR: / did not return the webapp" >&2
  exit 1
fi
echo "  webapp ok"

echo "Test 7: state survives a restart..."
docker rm -f "$NAME" >/dev/null
start_server
wait_healthy
if ! grep -q "No new migrations to apply" <<<"$(docker logs "$NAME" 2>&1)"; then
  echo "  ERROR: database was not reused after restart" >&2
  docker logs "$NAME" 2>&1 | tail -n 30
  exit 1
fi
echo "  restart ok"

echo ""
echo "=== All tests passed ==="
