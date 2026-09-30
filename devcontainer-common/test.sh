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

echo "=== Nexus mirror and login ==="
docker run --rm --user vscode -e NEXUS_DOCKER_URL=https://nexus.example.test "$IMAGE_REF" bash -c '
  set -e
  devcontainer-nexus-config
  conf=/etc/containers/registries.conf.d/99-nexus-mirror.conf
  [[ "$(grep -c "^location = \"nexus.example.test\"$" "$conf")" == 5 ]]
  sudo test ! -e /root/.config/containers/auth.json
  echo "mirror without login: OK"
'
docker run --rm --user vscode "$IMAGE_REF" bash -c '
  set -euo pipefail
  af=/root/.config/containers/auth.json
  want=$(printf "local-dev:sl_fakeTestPassword" | base64 -w0)
  fail() { echo "FAIL: $1"; exit 1; }
  entry() { sudo jq -r --arg h "$1" ".auths[\$h].auth // \"none\"" "$af"; }
  cfg() { env NEXUS_DOCKER_URL=https://nexus.example.test NEXUS_DOCKER_USERNAME=local-dev \
    NEXUS_DOCKER_PASSWORD=sl_fakeTestPassword "$@" devcontainer-nexus-config 2>&1; }

  sudo mkdir -p "$(dirname "$af")"
  echo "{\"auths\":{\"other.example\":{\"auth\":\"b3RoZXI6eA==\"}}}" | sudo tee "$af" >/dev/null
  sudo chmod 600 "$af"
  out=$(cfg)
  if grep -q sl_fakeTestPassword <<<"$out"; then fail "password printed"; fi
  [[ "$(sudo stat -c %a "$af")" == 600 ]] || fail "authfile mode"
  [[ "$(entry nexus.example.test)" == "$want" ]] || fail "login not written"
  [[ "$(entry other.example)" == "b3RoZXI6eA==" ]] || fail "other registry entry lost"
  cfg >/dev/null
  [[ "$(sudo jq ".auths | length" "$af")" == 2 ]] || fail "re-run changed entry count"
  echo "login merged and idempotent: OK"

  cr=$(printf "\r")
  cfg NEXUS_DOCKER_USERNAME="local-dev$cr" NEXUS_DOCKER_PASSWORD="sl_fakeTestPassword$cr" >/dev/null
  [[ "$(entry nexus.example.test)" == "$want" ]] || fail "CRLF not stripped"
  echo "CRLF stripped: OK"

  out=$(cfg NEXUS_DOCKER_PASSWORD=)
  grep -q WARNING <<<"$out" || fail "no warning for half-set login"
  [[ "$(entry nexus.example.test)" == none ]] || fail "stale login kept when password removed"
  echo "half-set login warns and clears stale login: OK"

  cfg >/dev/null
  cfg NEXUS_DOCKER_URL=https://nexus2.example.test >/dev/null
  [[ "$(entry nexus.example.test)" == none ]] || fail "old host login kept after host change"
  [[ "$(entry nexus2.example.test)" == "$want" ]] || fail "new host login missing"
  echo "host change moves login: OK"

  printf "not json" | sudo tee "$af" >/dev/null
  out=$(cfg) || fail "malformed authfile aborted the script"
  grep -q WARNING <<<"$out" || fail "no warning for malformed authfile"
  [[ "$(sudo cat "$af")" == "not json" ]] || fail "malformed authfile overwritten"
  echo "malformed authfile skipped: OK"
'
docker run --rm --user vscode -e NEXUS_DOCKER_URL="bad url;rm" "$IMAGE_REF" bash -c '
  set -e
  devcontainer-nexus-config
  [[ ! -e /etc/containers/registries.conf.d/99-nexus-mirror.conf ]]
  echo "invalid NEXUS_DOCKER_URL skipped: OK"
'

echo "=== podman namespaces ==="
DROPIN=/etc/containers/containers.conf.d/50-host-namespaces.conf
docker run --rm --user vscode -e DROPIN="$DROPIN" "$IMAGE_REF" bash -c '
  set -e
  devcontainer-podman-config
  grep -q "^netns = \"host\"" "$DROPIN"
  grep -q "^utsns = \"host\"" "$DROPIN"
  echo "no CAP_SYS_ADMIN: host namespaces: OK"
'
docker run --rm --privileged --user vscode -e DROPIN="$DROPIN" "$IMAGE_REF" bash -c '
  set -e
  devcontainer-podman-config
  [[ ! -e "$DROPIN" ]]
  echo "CAP_SYS_ADMIN: private namespaces: OK"
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
