#!/bin/bash
set -euo pipefail

IMAGE="${1:?Usage: test.sh <image-ref>}"

echo "Testing claude-agent-sre image..."

docker run --rm "$IMAGE" bash -c '
set -euo pipefail

for bin in claude node python3 git npm jq gh rg \
           kubectl kustomize helm helmfile cilium hubble \
           talosctl talhelper flux velero kubectl-cnpg falcoctl; do
  if ! command -v "$bin" &>/dev/null; then
    echo "FAIL: $bin not found"
    exit 1
  fi
  echo "OK: $bin found at $(which "$bin")"
done

claude --version
safe-chain --version
gh --version
rg --version
kubectl version --client
helm version
flux --version

# Verify helm plugins
helm plugin list | grep -q diff || { echo "FAIL: helm-diff plugin not found"; exit 1; }
echo "OK: helm-diff plugin installed"
helm plugin list | grep -q schema-gen || { echo "FAIL: helm-schema-gen plugin not found"; exit 1; }
echo "OK: helm-schema-gen plugin installed"

echo "All tests passed."
'
