#!/bin/bash
set -euo pipefail
IMAGE_REF="$1"

echo "Testing gastown-dev image..."
docker run --rm "$IMAGE_REF" bash -c '
  echo "=== Devcontainer Features ===" &&
  node --version &&
  python3 --version &&
  go version &&
  terraform version &&
  kubectl version --client &&
  helm version &&
  gh --version &&
  echo "=== CLI Tools ===" &&
  flux --version &&
  cilium version --client &&
  hubble version &&
  kustomize version &&
  helmfile --version &&
  talosctl version --client &&
  velero version --client-only &&
  task --version &&
  yq --version &&
  renovate --version &&
  sops --version &&
  pre-commit --version &&
  age --version
'
echo "All tools verified!"
