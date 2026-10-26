#!/bin/bash
# Test happy-server image: non-root user, PSA-restricted run (read-only rootfs),
# migrations, health endpoint, bundled webapp, state surviving a restart,
# Bytes columns reading back through PGlite, push suppression, no package
# managers shipped, dependency version floors and the script that applies them,
# the sharp native binding, and webapp assets.
# Usage: ./test.sh <image-ref>

set -euo pipefail

IMAGE_REF="${1:?Usage: $0 <image-ref>}"
NAME="happy-server-test-$$"
DATA_VOL="happy-server-test-data-$$"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PKG_DIR=/usr/local/lib/node_modules/happy-server-self-host

# The Dockerfile's annotated *_FLOOR args are the only list of floors.
mapfile -t FLOORS < <(awk '
  /^# renovate: datasource=npm depName=/ { pkg = $NF; sub(/^depName=/, "", pkg); next }
  /^ARG [A-Z_]+_FLOOR=/ && pkg != "" { v = $0; sub(/^[^=]*=/, "", v); print pkg "=" v }
  { pkg = "" }
' "$SRC_DIR/Dockerfile")
if [[ ${#FLOORS[@]} -eq 0 ]] || [[ ${#FLOORS[@]} -ne $(grep -c '^ARG [A-Z_]*_FLOOR=' "$SRC_DIR/Dockerfile") ]]; then
  echo "ERROR: every *_FLOOR arg in the Dockerfile needs a '# renovate: datasource=npm depName=...' line above it" >&2
  exit 1
fi

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

echo "Test 8: machine encryption key reads back..."
DEK_OUT=$(docker exec "$NAME" node -e '
const crypto = require("node:crypto");
const base = "http://127.0.0.1:3005";
(async () => {
  const { publicKey, privateKey } = crypto.generateKeyPairSync("ed25519");
  const challenge = crypto.randomBytes(32);
  const auth = await fetch(base + "/v1/auth", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      publicKey: Buffer.from(publicKey.export({ format: "jwk" }).x, "base64url").toString("base64"),
      challenge: challenge.toString("base64"),
      signature: crypto.sign(null, challenge, privateKey).toString("base64"),
    }),
  }).then((r) => r.json());
  const headers = { authorization: "Bearer " + auth.token, "content-type": "application/json" };
  const dek = crypto.randomBytes(105).toString("base64");
  await fetch(base + "/v1/machines", {
    method: "POST",
    headers,
    body: JSON.stringify({ id: "test-machine", metadata: "m", dataEncryptionKey: dek }),
  });
  const res = await fetch(base + "/v1/machines", { headers });
  const body = await res.json();
  console.log(res.status === 200 && body[0]?.dataEncryptionKey === dek ? "ok" : "status=" + res.status);
})();
' 2>&1)
if [[ "$DEK_OUT" != "ok" ]]; then
  echo "  ERROR: dataEncryptionKey did not round-trip: $DEK_OUT" >&2
  docker logs "$NAME" 2>&1 | grep -m 3 P2023 || true
  exit 1
fi
echo "  encryption key ok"

echo "Test 9: a connected coding session does not suppress its own push..."
PUSH_OUT=$(docker exec "$NAME" node -e '
const crypto = require("node:crypto");
const base = "http://127.0.0.1:3005";
(async () => {
  const { publicKey, privateKey } = crypto.generateKeyPairSync("ed25519");
  const challenge = crypto.randomBytes(32);
  const auth = await fetch(base + "/v1/auth", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      publicKey: Buffer.from(publicKey.export({ format: "jwk" }).x, "base64url").toString("base64"),
      challenge: challenge.toString("base64"),
      signature: crypto.sign(null, challenge, privateKey).toString("base64"),
    }),
  }).then((r) => r.json());
  const headers = { authorization: "Bearer " + auth.token, "content-type": "application/json" };
  const { session } = await fetch(base + "/v1/sessions", {
    method: "POST",
    headers,
    body: JSON.stringify({ tag: "push-test", metadata: "m" }),
  }).then((r) => r.json());
  const ws = new WebSocket("ws://127.0.0.1:3005/v1/updates/?EIO=4&transport=websocket");
  await new Promise((resolve, reject) => {
    ws.onerror = reject;
    ws.onmessage = ({ data }) => {
      if (data.startsWith("0")) ws.send("40" + JSON.stringify({ token: auth.token, clientType: "session-scoped", sessionId: session.id }));
      else if (data.startsWith("40")) resolve();
      else if (data.startsWith("44")) reject(new Error(data));
    };
  });
  const res = await fetch(base + "/v1/sessions/" + session.id + "/push-event", {
    method: "POST",
    headers,
    body: JSON.stringify({ kind: "done", title: "t", body: "b" }),
  });
  await new Promise((r) => setTimeout(r, 1000));
  ws.close();
  console.log(res.status === 200 ? session.id : "status=" + res.status);
})();
' 2>&1)
if [[ ! "$PUSH_OUT" =~ ^[a-z0-9]+$ ]]; then
  echo "  ERROR: push-event request failed: $PUSH_OUT" >&2
  exit 1
fi
if grep -q "Suppressed session-event push .* session $PUSH_OUT" <<<"$(docker logs "$NAME" 2>&1)"; then
  echo "  ERROR: the session's own socket suppressed its push" >&2
  exit 1
fi
if ! grep -q "No push tokens for user .* session $PUSH_OUT" <<<"$(docker logs "$NAME" 2>&1)"; then
  echo "  ERROR: push dispatch never reached the token lookup" >&2
  docker logs "$NAME" 2>&1 | grep -i push | tail -n 10
  exit 1
fi
echo "  push suppression ok"

echo "Test 10: npm, npx, corepack and yarn are not shipped..."
if ! docker run --rm --entrypoint sh "$IMAGE_REF" -c '
  for cmd in npm npx corepack yarn yarnpkg; do
    if command -v "$cmd"; then exit 1; fi
  done
  for path in /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/corepack /opt/yarn*; do
    if test -e "$path"; then echo "$path"; exit 1; fi
  done
'; then
  echo "  ERROR: a package manager is still in the image" >&2
  exit 1
fi
echo "  package managers absent ok"

echo "Test 11: dependency floors hold across the installed tree..."
if ! FLOOR_OUT=$(docker run --rm --entrypoint node -v "$SRC_DIR:/src:ro" "$IMAGE_REF" \
  /src/dependency-floors.cjs check "$PKG_DIR" "${FLOORS[@]}" 2>&1); then
  echo "  ERROR: $FLOOR_OUT" >&2
  exit 1
fi
echo "  dependency floors ok"

# Version check only: libbrotli1 comes in through curl's libcurl, not by name.
echo "Test 12: libbrotli1 is at or above 1.1.0-2+deb13u1..."
if ! docker run --rm --entrypoint sh "$IMAGE_REF" -c \
  'dpkg --compare-versions "$(dpkg-query -W -f="\${Version}" libbrotli1)" ge 1.1.0-2+deb13u1'; then
  echo "  ERROR: libbrotli1 is older than 1.1.0-2+deb13u1" >&2
  exit 1
fi
echo "  libbrotli1 ok"

echo "Test 13: sharp native binding loads and resizes..."
SHARP_OUT=$(docker run --rm --entrypoint node "$IMAGE_REF" -e '
const sharp = require("sharp");
(async () => {
  const src = await sharp({ create: { width: 8, height: 4, channels: 3, background: "#336699" } }).png().toBuffer();
  const meta = await sharp(src).metadata();
  const { data, info } = await sharp(src).resize(4, 2).ensureAlpha().raw().toBuffer({ resolveWithObject: true });
  console.log(meta.width === 8 && info.channels === 4 && data.length === 32 ? "ok" : "unexpected");
})().catch((e) => console.log(String(e)));
' 2>&1)
if [[ "$SHARP_OUT" != "ok" ]]; then
  echo "  ERROR: sharp did not resize an image: $SHARP_OUT" >&2
  exit 1
fi
echo "  sharp ok"

echo "Test 14: webapp assets are served..."
ASSET=$(docker exec "$NAME" find webapp -type f -name '*.js' -regex '[A-Za-z0-9_./-]*' -print -quit)
# Unknown paths fall back to index.html, so compare bytes with the file in the image.
if [[ -z "$ASSET" ]] || ! in_container_get "/${ASSET#webapp/}" | docker exec -i "$NAME" cmp - "$ASSET"; then
  echo "  ERROR: webapp asset ${ASSET:-<none found>} was not served" >&2
  exit 1
fi
echo "  assets ok"

echo "Test 15: dependency-floors.cjs applies and checks floors..."
if ! FLOORS_TEST_OUT=$(docker run --rm --entrypoint node -v "$SRC_DIR:/src:ro" "$IMAGE_REF" \
  --test /src/dependency-floors.test.cjs 2>&1); then
  echo "  ERROR: dependency-floors.cjs tests failed" >&2
  echo "$FLOORS_TEST_OUT" | tail -n 40 >&2
  exit 1
fi
echo "  floors script ok"

echo ""
echo "=== All tests passed ==="
