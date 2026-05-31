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

# Functional pre-commit test: use a local hook so no network or hook env install needed.
# Verifies python, pre-commit, and git all work together end-to-end.
TMPDIR=$(mktemp -d)
cd "$TMPDIR"
git init -q
git config user.email "test@test"
git config user.name "test"
cat > .pre-commit-config.yaml <<EOF
repos:
  - repo: local
    hooks:
      - id: smoke
        name: smoke
        entry: echo
        language: system
        pass_filenames: false
EOF
touch test.txt
git add .
pre-commit run --all-files smoke
echo "OK: pre-commit functional test passed"
cd /
rm -rf "$TMPDIR"

echo "All tests passed."
'
