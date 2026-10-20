#!/bin/bash
# Test script for llm-tool-guard container
# Usage: ./test.sh <image-ref>

set -euo pipefail

IMAGE_REF="${1:?Usage: $0 <image-ref>}"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SUFFIX="$$"
NETWORK="llm-tool-guard-test-$SUFFIX"
VALKEY="llm-tool-guard-valkey-$SUFFIX"
GUARD="llm-tool-guard-test-$SUFFIX"
VOLUME="llm-tool-guard-hf-$SUFFIX"
WEIGHTS="llm-tool-guard-weights-$SUFFIX"
WEIGHTS_IMAGE="llm-tool-guard-model-test:$SUFFIX"
HUB="$(mktemp -d)"
TOKEN="test-token-$SUFFIX"
# renovate: datasource=docker depName=docker.io/valkey/valkey
VALKEY_IMAGE="docker.io/valkey/valkey:9.1.2@sha256:418652cfb58ef879d4978c33553735d7147016032d5aefaa14c828e611eb9dfd"

# Uncompressed image ceiling: fails loudly if a CUDA torch wheel or model weights land in the image.
MAX_IMAGE_BYTES=$((2000 * 1000 * 1000))

# cleanup removes the test containers, network, model cache volume and weights copy, ignoring any that are already gone.
cleanup() {
  echo "Cleaning up..."
  docker rm -f "$GUARD" "$VALKEY" "$WEIGHTS" >/dev/null 2>&1 || true
  docker network rm "$NETWORK" >/dev/null 2>&1 || true
  docker volume rm "$VOLUME" >/dev/null 2>&1 || true
  docker rmi "$WEIGHTS_IMAGE" >/dev/null 2>&1 || true
  chmod -R u+w "$HUB" >/dev/null 2>&1 || true
  rm -rf "$HUB" >/dev/null 2>&1 || true
}
trap cleanup EXIT

# Mount arguments that put the model cache at HF_HOME; Test 11 swaps them for the weights image layout.
HF_MOUNT=(-v "$VOLUME:/app/.cache/huggingface")

# start_guard runs the scanner against Valkey with the HF_MOUNT model cache; extra args are passed to docker run.
start_guard() {
  docker rm -f "$GUARD" >/dev/null 2>&1 || true
  docker run -d \
    --name "$GUARD" \
    --network "$NETWORK" \
    -p 127.0.0.1::8080 \
    "${HF_MOUNT[@]}" \
    -e VALKEY_URL="redis://$VALKEY:6379/0" \
    -e AUTH_TOKEN="$TOKEN" \
    -e JEV_MODE=off \
    "$@" \
    "$IMAGE_REF" >/dev/null
  BASE="http://$(docker port "$GUARD" 8080/tcp | head -n 1)"
}

# wait_for polls a URL until it answers 200 or the timeout in seconds runs out; it stops early once a model load has failed.
wait_for() {
  local url="$1" timeout="$2" elapsed=0
  while [[ $elapsed -lt $timeout ]]; do
    if curl -sf "$url" >/dev/null 2>&1; then
      echo "  OK after ${elapsed}s"
      return 0
    fi
    if [[ "$(curl -s -o /dev/null -w '%{http_code}' "$BASE/healthz")" == "503" ]]; then
      echo "  ERROR: model load failed" >&2
      docker logs "$GUARD"
      return 1
    fi
    sleep 5
    elapsed=$((elapsed + 5))
  done
  echo "  ERROR: timeout waiting for $url" >&2
  docker logs "$GUARD"
  return 1
}

echo "=== LLM Tool Guard Container Tests ==="
echo "Image: $IMAGE_REF"
echo ""

echo "Test 1: scanner_types.py matches llm-guard's..."
if ! cmp -s "$DIR/app/scanner_types.py" "$DIR/../llm-guard/app/scanner_types.py"; then
  echo "  ERROR: llm-tool-guard/app/scanner_types.py differs from llm-guard/app/scanner_types.py; copy it over" >&2
  exit 1
fi
echo "  identical OK"

echo "Test 2: runs as a non-root user..."
UID_IN_IMAGE=$(docker run --rm --entrypoint id "$IMAGE_REF" -u)
if [[ "$UID_IN_IMAGE" != "1000" ]]; then
  echo "  ERROR: image runs as uid $UID_IN_IMAGE" >&2
  exit 1
fi
echo "  uid 1000 OK"

echo "Test 3: torch is the CPU build..."
TORCH_CUDA=$(docker run --rm --entrypoint python "$IMAGE_REF" -c "import torch; print(torch.version.cuda)")
if [[ "$TORCH_CUDA" != "None" ]]; then
  echo "  ERROR: image contains a CUDA torch build (torch.version.cuda=$TORCH_CUDA)" >&2
  exit 1
fi
echo "  torch.version.cuda=None OK"

echo "Test 4: image size under ceiling..."
IMAGE_BYTES=$(docker image inspect "$IMAGE_REF" --format '{{.Size}}')
if [[ "$IMAGE_BYTES" -ge "$MAX_IMAGE_BYTES" ]]; then
  echo "  ERROR: image is ${IMAGE_BYTES} bytes, ceiling is ${MAX_IMAGE_BYTES}" >&2
  exit 1
fi
echo "  ${IMAGE_BYTES} bytes (ceiling ${MAX_IMAGE_BYTES}) OK"

echo "Test 5: start Valkey and the scanner (cold model cache)..."
docker network create "$NETWORK" >/dev/null
docker volume create "$VOLUME" >/dev/null
docker run -d --name "$VALKEY" --network "$NETWORK" --user 999:999 --entrypoint valkey-server \
  "$VALKEY_IMAGE" --save "" --appendonly no >/dev/null
start_guard
echo "  /healthz (max 120s)..."
wait_for "$BASE/healthz" 120
echo "  /readyz (max 600s, includes the first model download)..."
wait_for "$BASE/readyz" 600

echo "Test 6: scan API, auth and verdict cache..."
python3 "$DIR/tests/smoke.py" "$BASE" "$TOKEN" scan

echo "Test 7: scan time budget..."
start_guard -e HF_HUB_OFFLINE=1 -e SCAN_TIMEOUT_SECONDS=0.5 -e WINDOW_TOKENS=16 -e WINDOW_OVERLAP=4
wait_for "$BASE/readyz" 120
python3 "$DIR/tests/smoke.py" "$BASE" "$TOKEN" budget

echo "Test 8: restart offline from the warm model cache..."
start_guard -e HF_HUB_OFFLINE=1
wait_for "$BASE/readyz" 120
python3 "$DIR/tests/smoke.py" "$BASE" "$TOKEN" cached

echo "Test 9: scans keep working with Valkey down..."
docker stop "$VALKEY" >/dev/null
python3 "$DIR/tests/smoke.py" "$BASE" "$TOKEN" cache-down

echo "Test 10: unit tests..."
docker run --rm \
  -v "$DIR/tests:/tests:ro" \
  -e PYTHONDONTWRITEBYTECODE=1 \
  --entrypoint sh \
  "$IMAGE_REF" \
  -c 'pip install --user --no-cache-dir --quiet --disable-pip-version-check --no-warn-script-location \
    --only-binary :all: --require-hashes -r /tests/requirements-test.txt \
    && python -m pytest -p no:cacheprovider -q /tests'
echo "  unit tests OK"

echo "Test 11: starts and scans offline with the weights image read-only at HF_HOME/hub..."
MODEL_REVISION=$(sed -n 's/^ARG MODEL_REVISION=//p' "$DIR/../llm-tool-guard-model/Dockerfile")
docker build -q -t "$WEIGHTS_IMAGE" "$DIR/../llm-tool-guard-model" >/dev/null
# The image has no shell or command; the name given to create is never run.
docker create --name "$WEIGHTS" "$WEIGHTS_IMAGE" none >/dev/null
docker cp "$WEIGHTS:/." "$HUB/"
chmod 755 "$HUB"
docker start "$VALKEY" >/dev/null
HF_MOUNT=(--tmpfs /app/.cache/huggingface:mode=1777 -v "$HUB:/app/.cache/huggingface/hub:ro")
start_guard -e HF_HUB_OFFLINE=1
wait_for "$BASE/readyz" 120
if docker exec -u 0 "$GUARD" touch /app/.cache/huggingface/hub/probe 2>/dev/null; then
  echo "  ERROR: the model cache is writable" >&2
  exit 1
fi
echo "  model cache is read-only OK"
python3 "$DIR/tests/smoke.py" "$BASE" "$TOKEN" scan
if ! grep -qF "model revision $MODEL_REVISION" <<<"$(docker logs "$GUARD" 2>&1)"; then
  echo "  ERROR: scanner did not report model revision $MODEL_REVISION" >&2
  docker logs "$GUARD"
  exit 1
fi
echo "  model revision $MODEL_REVISION OK"

echo ""
echo "=== All tests passed ==="
