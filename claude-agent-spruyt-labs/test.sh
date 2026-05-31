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
node -e "console.log(\"OK: node executes\")"
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

# Functional pre-commit test that actually installs hook environments.
# Uses a node-language hook (markdownlint) and a python-language hook
# (end-of-file-fixer) so pre-commit builds and runs real node + python hook
# envs — not a "language: system / echo" no-op. This exercises the full path
# agents depend on (clone hook repo, build env, run hook).
TMPDIR=$(mktemp -d)
cd "$TMPDIR"
git init -q
git config user.email "test@test"
git config user.name "test"
cat > .pre-commit-config.yaml <<EOF
repos:
  - repo: https://github.com/igorshubovych/markdownlint-cli
    rev: v0.48.0
    hooks:
      - id: markdownlint
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v6.0.0
    hooks:
      - id: end-of-file-fixer
EOF
printf "# Title\n\nContent.\n" > README.md
git add .
pre-commit run --all-files
echo "OK: pre-commit functional test passed (node + python hook envs built and ran)"
cd /
rm -rf "$TMPDIR"

echo "All tests passed."
'
