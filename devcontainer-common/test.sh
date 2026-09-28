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
  podman --version &&
  [[ "$(podman --version | grep -oE "[0-9]+" | head -1)" -ge 5 ]] &&
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
  "--network=container:x" "--network none" "--pid=host" "--pid=container:x" "--ipc=container:x" \
  "--userns=host" "--userns=keep-id" "--cap-add=ALL" "--cap-add=SYS_ADMIN" "--cap-add SYS_ADMIN" \
  "--pod=p" "-v /run/podman/podman.sock:/s"; do
  rc=0
  # shellcheck disable=SC2086
  docker run --rm --user vscode "$IMAGE_REF" agent-run $args alpine true >/dev/null 2>&1 || rc=$?
  if [[ $rc -ne 64 ]]; then
    echo "agent-run did not reject '$args' (exit $rc)"
    exit 1
  fi
  echo "rejected: $args"
done

for net in host container:x; do
  rc=0
  docker run --rm --user vscode -e AGENT_RUN_NET="$net" "$IMAGE_REF" agent-run alpine true >/dev/null 2>&1 || rc=$?
  if [[ $rc -ne 64 ]]; then
    echo "agent-run did not reject AGENT_RUN_NET=$net (exit $rc)"
    exit 1
  fi
  echo "rejected: AGENT_RUN_NET=$net"
done

# Needs a privileged outer container for nested podman. Passes in CI and Coder;
# a WSL devcontainer cannot run the bridge case (read-only ping_group_range sysctl).
echo "=== agent-run runtime ==="
docker run --rm --privileged -v /var/lib/containers --user vscode "$IMAGE_REF" bash -c '
  set -euo pipefail
  command -v nft >/dev/null && echo "nft: OK"
  printf "[containers]\ncgroups = \"disabled\"\n\n[engine]\ncgroup_manager = \"cgroupfs\"\n" |
    sudo tee /etc/containers/containers.conf >/dev/null
  AGENT_RUN_NET=none agent-run docker.io/library/alpine:3 true
  echo "agent-run (no network, userns=auto): OK"
  agent-run docker.io/library/alpine:3 ip link show eth0 >/dev/null
  echo "agent-run (bridge network): OK"
'

echo "All tests passed!"
