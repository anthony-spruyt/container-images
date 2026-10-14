#!/bin/bash
# Test script for llm-tool-guard-model container
# Usage: ./test.sh <image-ref>

set -euo pipefail

IMAGE_REF="${1:?Usage: $0 <image-ref>}"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONTAINER="llm-tool-guard-model-test-$$"
OUT="$(mktemp -d)"
MODEL_DIR="models--Horizon-Labs--prompt-injection-guard-base"
FILES=(config.json model.safetensors special_tokens_map.json tokenizer.json tokenizer_config.json)

# Uncompressed image ceiling: fails loudly if the ONNX exports land in the image.
MAX_IMAGE_BYTES=$((1400 * 1000 * 1000))

# cleanup removes the container and the copied cache, ignoring any that are already gone.
cleanup() {
  echo "Cleaning up..."
  docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
  chmod -R u+w "$OUT" >/dev/null 2>&1 || true
  rm -rf "$OUT" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "=== LLM Tool Guard Model Container Tests ==="
echo "Image: $IMAGE_REF"
echo ""

# The image has no shell or command; the name given to create is never run.
docker create --name "$CONTAINER" "$IMAGE_REF" none >/dev/null
docker cp "$CONTAINER:/." "$OUT/"

echo "Test 1: refs/main holds the pinned revision..."
PINNED=$(sed -n 's/^ARG MODEL_REVISION=//p' "$DIR/Dockerfile")
[[ "$PINNED" =~ ^[0-9a-f]{40}$ ]] || {
  echo "  ERROR: no 40-character MODEL_REVISION in the Dockerfile" >&2
  exit 1
}
REF=$(cat "$OUT/$MODEL_DIR/refs/main")
if [[ "$REF" != "$PINNED" ]]; then
  echo "  ERROR: refs/main is '$REF', Dockerfile pins '$PINNED'" >&2
  exit 1
fi
echo "  $PINNED OK"

echo "Test 2: the snapshot holds exactly the files the scanner loads..."
SNAPSHOT="$OUT/$MODEL_DIR/snapshots/$PINNED"
mapfile -t FOUND < <(LC_ALL=C ls -1 "$SNAPSHOT")
if [[ "${FOUND[*]}" != "${FILES[*]}" ]]; then
  echo "  ERROR: snapshot holds '${FOUND[*]}', expected '${FILES[*]}'" >&2
  exit 1
fi
for file in "${FILES[@]}"; do
  if [[ ! -s "$SNAPSHOT/$file" ]]; then
    echo "  ERROR: $file is missing or empty (broken link into blobs/)" >&2
    exit 1
  fi
done
echo "  ${FILES[*]} OK"

echo "Test 3: image size under ceiling..."
IMAGE_BYTES=$(docker image inspect "$IMAGE_REF" --format '{{.Size}}')
if [[ "$IMAGE_BYTES" -ge "$MAX_IMAGE_BYTES" ]]; then
  echo "  ERROR: image is ${IMAGE_BYTES} bytes, ceiling is ${MAX_IMAGE_BYTES}" >&2
  exit 1
fi
echo "  ${IMAGE_BYTES} bytes (ceiling ${MAX_IMAGE_BYTES}) OK"

echo ""
echo "=== All tests passed ==="
