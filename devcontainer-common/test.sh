#!/bin/bash
set -euo pipefail
IMAGE_REF="$1"

echo "Testing devcontainer-common image..."

docker run --rm "$IMAGE_REF" bash -c '
  echo "=== Devcontainer Features ===" &&
  node --version &&
  python3 --version &&
  pre-commit --version &&
  mdformat --version &&
  pip show mdformat-frontmatter &&
  pip show mdformat-admon &&
  gh --version &&
  echo "=== Podman ===" &&
  command -v podman &&
  echo "=== Scripts ===" &&
  test -x /usr/local/bin/agent-run && echo "agent-run: OK" &&
  test -x /usr/local/bin/devcontainer-post-create && echo "devcontainer-post-create: OK"
'

echo "=== Podman wrapper ==="
docker run --rm --user vscode "$IMAGE_REF" bash -c '
  set -e
  [[ "$(command -v podman)" == /usr/local/bin/podman ]]
  [[ "$(command -v docker)" == /usr/local/bin/docker ]]
  echo "podman/docker resolve to sudo wrappers: OK"
'

echo "=== userns=auto subordinate IDs ==="
docker run --rm "$IMAGE_REF" bash -c '
  set -e
  [[ "$(grep -c "^containers:" /etc/subuid)" == 1 ]]
  [[ "$(grep -c "^containers:" /etc/subgid)" == 1 ]]
  echo "subuid/subgid: OK"
'

echo "=== agent-run policy ==="
for args in "--privileged" "--net=host" "--net host" "--network=host" "--network host" \
  "--pid=host" "--userns=host" "--cap-add=ALL" "-v /run/podman/podman.sock:/s"; do
  rc=0
  # shellcheck disable=SC2086
  docker run --rm --user vscode "$IMAGE_REF" agent-run $args alpine true >/dev/null 2>&1 || rc=$?
  if [[ $rc -ne 64 ]]; then
    echo "agent-run did not reject '$args' (exit $rc)"
    exit 1
  fi
  echo "rejected: $args"
done

echo "All tests passed!"
