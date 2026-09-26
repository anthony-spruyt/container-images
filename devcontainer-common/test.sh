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
  test -x /usr/local/bin/devcontainer-post-create && echo "devcontainer-post-create: OK" &&
  echo "=== Claude sandbox ===" &&
  for bin in bwrap socat sandbox-lint ssh-via-sandbox-proxy claude-statusline; do
    command -v "$bin" || { echo "FAIL: $bin not found"; exit 1; }
  done &&
  jq empty /etc/claude-code/managed-settings.json && echo "managed-settings.json: OK" &&
  test -d /var/tmp/claude && echo "/var/tmp/claude: OK"
'

echo "All tests passed!"
