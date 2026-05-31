#!/bin/bash
set -euo pipefail

IMAGE="${1:?Usage: test.sh <image-ref>}"

echo "Testing claude-agent-spruyt-labs image..."

docker run --rm "$IMAGE" bash -c '
set -euo pipefail

for bin in claude node python3 git npm jq gh rg go pre-commit \
           kubectl kustomize helm helmfile cilium \
           talosctl flux velero kubectl-cnpg falcoctl; do
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
go version
pre-commit --version
kubectl version --client
helm version
flux --version

# Verify helm plugins
helm plugin list | grep -q diff || { echo "FAIL: helm-diff plugin not found"; exit 1; }
echo "OK: helm-diff plugin installed"
helm plugin list | grep -q schema-gen || { echo "FAIL: helm-schema-gen plugin not found"; exit 1; }
echo "OK: helm-schema-gen plugin installed"

# Verify claude can actually execute (catches missing libatomic1 and similar)
if ! claude --version --no-update-check >/dev/null 2>&1; then
  echo "FAIL: claude binary fails at runtime (missing shared libs?)"
  ldd "$(which claude)" 2>/dev/null || true
  exit 1
fi
echo "OK: claude runtime smoke test passed"

echo "All tests passed."
'
