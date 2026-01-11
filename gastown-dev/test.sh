#!/bin/bash
set -euo pipefail
IMAGE_REF="$1"

echo "Testing gastown-dev image..."

# Test CLI tools are available (skip entrypoint since we don't need Docker here)
echo "=== Testing CLI Tools ==="
docker run --rm --entrypoint "" "$IMAGE_REF" bash -c '
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

# Test Docker-in-Docker actually works
echo "=== Testing Docker-in-Docker ==="
docker run --rm --privileged "$IMAGE_REF" bash -c '
  # Wait for Docker daemon to start (entrypoint starts it)
  echo "Waiting for Docker daemon to start..."
  timeout 30 bash -c "until docker info >/dev/null 2>&1; do sleep 1; done"
  echo "Docker daemon is running"
  docker run --rm hello-world | grep -q "Hello from Docker"
  echo "Docker-in-Docker verified!"
'

echo "All tests passed!"
