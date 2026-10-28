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
MODEL="llm-tool-guard-model-$SUFFIX"
MODEL_IMAGE="llm-tool-guard-model-test:$SUFFIX"
HUB="$(mktemp -d)"
TOKEN="test-token-$SUFFIX"
# renovate: datasource=docker depName=docker.io/valkey/valkey
VALKEY_IMAGE="docker.io/valkey/valkey:9.1.3@sha256:3add1a336a920ea54770a001ab6feb3da5fceea96a40373a3a2cd469b815f0b7"

# Uncompressed image ceiling: fails loudly if torch or model weights land in the image.
MAX_IMAGE_BYTES=$((1500 * 1000 * 1000))

# cleanup removes the test containers, network and model image copy, ignoring any that are already gone.
cleanup() {
  echo "Cleaning up..."
  docker rm -f "$GUARD" "$VALKEY" "$MODEL" >/dev/null 2>&1 || true
  docker network rm "$NETWORK" >/dev/null 2>&1 || true
  docker rmi "$MODEL_IMAGE" >/dev/null 2>&1 || true
  chmod -R u+w "$HUB" >/dev/null 2>&1 || true
  rm -rf "$HUB" >/dev/null 2>&1 || true
}
trap cleanup EXIT

# Mount arguments that put the model image's files at HF_HOME/hub; set once the model image is built.
HF_MOUNT=()

# start_guard runs the scanner on DEVICE (CPU unless set; empty keeps the image default) against Valkey with the
# HF_MOUNT model cache, offline; extra args are passed to docker run.
start_guard() {
  docker rm -f "$GUARD" >/dev/null 2>&1 || true
  docker run -d \
    --name "$GUARD" \
    --network "$NETWORK" \
    -p 127.0.0.1::8080 \
    "${HF_MOUNT[@]}" \
    -e SCANNER_DEVICE="${DEVICE-CPU}" \
    -e HF_HUB_OFFLINE=1 \
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

# openvino_pin prints the OpenVINO version a pyproject.toml pins.
openvino_pin() {
  sed -n 's/^ *"openvino==\(.*\)",$/\1/p' "$1"
}

echo "=== LLM Tool Guard Container Tests ==="
echo "Image: $IMAGE_REF"
echo ""

echo "Test 1: runs as a non-root user..."
UID_IN_IMAGE=$(docker run --rm --entrypoint id "$IMAGE_REF" -u)
if [[ "$UID_IN_IMAGE" != "1000" ]]; then
  echo "  ERROR: image runs as uid $UID_IN_IMAGE" >&2
  exit 1
fi
echo "  uid 1000 OK"

echo "Test 2: the scanner and the model converter pin the same OpenVINO..."
RUNTIME_PIN=$(openvino_pin "$DIR/pyproject.toml")
CONVERTER_PIN=$(openvino_pin "$DIR/../llm-tool-guard-model/convert/pyproject.toml")
if [[ -z "$RUNTIME_PIN" || "$RUNTIME_PIN" != "$CONVERTER_PIN" ]]; then
  echo "  ERROR: scanner pins openvino '$RUNTIME_PIN', converter pins '$CONVERTER_PIN'" >&2
  exit 1
fi
echo "  openvino $RUNTIME_PIN OK"

echo "Test 3: the GPU runtime is complete and named in the image..."
# No GPU here, so this checks what a GPU run needs from the image: the driver loads its libraries, and the baked
# INTEL_GPU_RUNTIME names the packages that are installed.
if ! docker run --rm --entrypoint sh "$IMAGE_REF" -c '
  set -eu
  icd="$(cat /etc/OpenCL/vendors/intel.icd)"
  if ldd "$icd" | grep -q "not found"; then echo "  ERROR: $icd has unresolved libraries" >&2; exit 1; fi
  for library in libigc.so.2 libigdfcl.so.2; do
    ldconfig -p | grep -q "$library" || { echo "  ERROR: $library is not in the linker cache" >&2; exit 1; }
  done
  for package in intel-opencl-icd intel-igc-opencl-2 libigdgmm12; do
    version="$(dpkg-query -W -f="\${Version}" "$package")"
    case "$INTEL_GPU_RUNTIME" in
      *"${version%-0}"*) ;;
      *) echo "  ERROR: INTEL_GPU_RUNTIME \"$INTEL_GPU_RUNTIME\" lacks $package $version" >&2; exit 1 ;;
    esac
  done
  echo "  $INTEL_GPU_RUNTIME"
'; then
  exit 1
fi
echo "  GPU runtime OK"

echo "Test 4: image size under ceiling..."
IMAGE_BYTES=$(docker image inspect "$IMAGE_REF" --format '{{.Size}}')
if [[ "$IMAGE_BYTES" -ge "$MAX_IMAGE_BYTES" ]]; then
  echo "  ERROR: image is ${IMAGE_BYTES} bytes, ceiling is ${MAX_IMAGE_BYTES}" >&2
  exit 1
fi
echo "  ${IMAGE_BYTES} bytes (ceiling ${MAX_IMAGE_BYTES}) OK"

echo "Test 5: start Valkey and the scanner on the model image, read-only at HF_HOME/hub..."
MODEL_REVISION=$(sed -n 's/^ARG MODEL_REVISION=//p' "$DIR/../llm-tool-guard-model/Dockerfile")
docker build -q -t "$MODEL_IMAGE" "$DIR/../llm-tool-guard-model" >/dev/null
# The image has no shell or command; the name given to create is never run.
docker create --name "$MODEL" "$MODEL_IMAGE" none >/dev/null
docker cp "$MODEL:/." "$HUB/"
chmod 755 "$HUB"
HF_MOUNT=(--tmpfs /app/.cache/huggingface:mode=1777 -v "$HUB:/app/.cache/huggingface/hub:ro")
docker network create "$NETWORK" >/dev/null
docker run -d --name "$VALKEY" --network "$NETWORK" --user 999:999 --entrypoint valkey-server \
  "$VALKEY_IMAGE" --save "" --appendonly no >/dev/null
start_guard
echo "  /healthz (max 120s)..."
wait_for "$BASE/healthz" 120
echo "  /readyz (max 120s)..."
wait_for "$BASE/readyz" 120
if docker exec -u 0 "$GUARD" touch /app/.cache/huggingface/hub/probe 2>/dev/null; then
  echo "  ERROR: the model cache is writable" >&2
  exit 1
fi
echo "  model cache is read-only OK"
if ! grep -qF "model revision $MODEL_REVISION" <<<"$(docker logs "$GUARD" 2>&1)"; then
  echo "  ERROR: scanner did not report model revision $MODEL_REVISION" >&2
  docker logs "$GUARD"
  exit 1
fi
echo "  model revision $MODEL_REVISION OK"

echo "Test 6: scan API, auth and verdict cache..."
python3 "$DIR/tests/smoke.py" "$BASE" "$TOKEN" scan

echo "Test 7: scan time budget..."
start_guard -e SCAN_TIMEOUT_SECONDS=0.5 -e WINDOW_TOKENS=16 -e WINDOW_OVERLAP=4
wait_for "$BASE/readyz" 120
python3 "$DIR/tests/smoke.py" "$BASE" "$TOKEN" budget

echo "Test 8: a restart keeps serving the cached verdicts..."
start_guard
wait_for "$BASE/readyz" 120
python3 "$DIR/tests/smoke.py" "$BASE" "$TOKEN" cached

echo "Test 9: scans keep working with Valkey down..."
docker stop "$VALKEY" >/dev/null
python3 "$DIR/tests/smoke.py" "$BASE" "$TOKEN" cache-down

echo "Test 10: unit tests..."
# The image has no pip: this throwaway container bootstraps one from the interpreter's bundled wheel.
docker run --rm \
  -v "$DIR/tests:/tests:ro" \
  -e PYTHONDONTWRITEBYTECODE=1 \
  --entrypoint sh \
  "$IMAGE_REF" \
  -c 'python -m ensurepip --user >/dev/null && python -m pip install --user --no-cache-dir --quiet --disable-pip-version-check --no-warn-script-location \
    --only-binary :all: --require-hashes -r /tests/requirements-test.txt \
    && python -m pytest -p no:cacheprovider -q /tests'
echo "  unit tests OK"

echo "Test 11: the default device is the GPU, and with none the load fails instead of falling back to the CPU..."
DEVICE="" start_guard
ELAPSED=0
until [[ "$(curl -s -o /dev/null -w '%{http_code}' "$BASE/healthz")" == "503" ]]; do
  if [[ $ELAPSED -ge 120 ]]; then
    echo "  ERROR: /healthz never reported a failed load" >&2
    docker logs "$GUARD"
    exit 1
  fi
  sleep 5
  ELAPSED=$((ELAPSED + 5))
done
if [[ "$(curl -s -o /dev/null -w '%{http_code}' "$BASE/readyz")" == "200" ]]; then
  echo "  ERROR: the scanner is ready without a GPU" >&2
  exit 1
fi
echo "  load failed after ${ELAPSED}s and /readyz is not ready OK"

echo "Test 12: pip is not in the image..."
if ! docker run --rm --entrypoint python "$IMAGE_REF" -c \
  'import importlib.util, shutil, sys; sys.exit(importlib.util.find_spec("pip") is not None or shutil.which("pip") is not None)'; then
  echo "  ERROR: pip is installed" >&2
  exit 1
fi
echo "  no pip OK"

echo ""
echo "=== All tests passed ==="
