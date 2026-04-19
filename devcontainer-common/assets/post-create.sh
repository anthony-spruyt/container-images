#!/bin/bash
set -euo pipefail

# devcontainer-post-create: runtime setup for devcontainer-common based images.
# Packages (podman, pre-commit, gh, node, python) are pre-installed.
# This script handles runtime configuration that requires workspace context.
#
# Usage: devcontainer-post-create [workspace-dir]

WORKSPACE="${1:-.}"
DEVCONTAINER_DIR="$WORKSPACE/.devcontainer"

PASSED=0
FAILED=0
pass() {
  echo "✓ $1"
  PASSED=$((PASSED + 1))
}
fail() {
  echo "✗ $1"
  FAILED=$((FAILED + 1))
}

# --- Runtime Configuration ---

git config --global --add safe.directory '*'

sudo mkdir -p /etc/containers/registries.conf.d /etc/containers/containers.conf.d
sudo chmod a+rx /etc/containers /etc/containers/registries.conf.d /etc/containers/containers.conf.d

git ls-files -z '*.sh' | xargs -0 -r chmod +x 2>/dev/null || true

# renovate: datasource=npm depName=@aikidosec/safe-chain
SAFE_CHAIN_VERSION="1.4.9"
echo "Installing safe-chain ${SAFE_CHAIN_VERSION}..."
npm install -g "@aikidosec/safe-chain@${SAFE_CHAIN_VERSION}"
safe-chain setup
safe-chain setup-ci
export PATH="$HOME/.safe-chain/shims:$PATH"

echo "Installing pre-commit hooks..."
git config --unset-all core.hooksPath 2>/dev/null || true
pre-commit install --install-hooks

echo "Installing Claude Code CLI..."
curl -fsSL https://claude.ai/install.sh | bash
export PATH="$HOME/.local/bin:$PATH"
# shellcheck disable=SC2016
grep -q 'local/bin' "$HOME/.bashrc" 2>/dev/null || echo 'export PATH="$HOME/.local/bin:$PATH"' >>"$HOME/.bashrc"

# Podman userns config
mkdir -p "$HOME/.config/containers/containers.conf.d"
cat >"$HOME/.config/containers/containers.conf.d/10-userns.conf" <<'CONTAINERS_CONF'
[containers]
userns = "keep-id"
CONTAINERS_CONF

# Storage and cgroup configuration (Kata vs WSL2 detection)
if [ -b /dev/containers-disk ]; then
  if ! sudo blkid /dev/containers-disk >/dev/null 2>&1; then
    sudo mkfs.ext4 -q -L containers /dev/containers-disk
  fi
  sudo mkdir -p /var/lib/containers
  sudo mountpoint -q /var/lib/containers || sudo mount -o noatime /dev/containers-disk /var/lib/containers
  rm -rf "$HOME/.local/share/containers/storage" "$HOME/.config/containers/storage.conf"
  sudo mkdir -p /etc/containers
  sudo tee /etc/containers/storage.conf >/dev/null <<'ROOTFUL_STORAGE_CONF'
[storage]
driver = "overlay"
runroot = "/run/containers/storage"
graphroot = "/var/lib/containers/storage"
ROOTFUL_STORAGE_CONF
  sudo tee /etc/containers/containers.conf >/dev/null <<'CONTAINERS_CONF'
[containers]
cgroups = "disabled"

[engine]
cgroup_manager = "cgroupfs"
CONTAINERS_CONF
  grep -q 'alias podman=' "$HOME/.bashrc" 2>/dev/null || echo 'alias podman="sudo podman"' >>"$HOME/.bashrc"
else
  sudo mkdir -p /etc/containers
  sudo tee /etc/containers/storage.conf >/dev/null <<'ROOTFUL_STORAGE_CONF'
[storage]
driver = "overlay"
runroot = "/run/containers/storage"
graphroot = "/var/lib/containers/storage"
ROOTFUL_STORAGE_CONF
  sudo tee /etc/containers/containers.conf >/dev/null <<'CONTAINERS_CONF'
[containers]
cgroups = "disabled"

[engine]
cgroup_manager = "cgroupfs"
CONTAINERS_CONF
  sudo chown root:root /var/lib/containers
  mkdir -p "$HOME/.config/containers"
  cat >"$HOME/.config/containers/storage.conf" <<STORAGE_CONF
[storage]
driver = "overlay"
runroot = "/run/user/$(id -u)/containers"
graphroot = "$HOME/.local/share/containers/storage"
[storage.options.overlay]
mount_program = "/usr/bin/fuse-overlayfs"
STORAGE_CONF
  grep -q 'alias podman=' "$HOME/.bashrc" 2>/dev/null || echo 'alias podman="sudo podman"' >>"$HOME/.bashrc"
fi

# Registry allow-list
mkdir -p "$HOME/.config/containers/registries.conf.d"
cat >"$HOME/.config/containers/registries.conf.d/10-allow-list.conf" <<'REGISTRIES_CONF'
unqualified-search-registries = []
short-name-mode = "enforcing"

[[registry]]
location = "docker.io"

[[registry]]
location = "ghcr.io"

[[registry]]
location = "quay.io"

[[registry]]
location = "registry.k8s.io"

[[registry]]
location = "mcr.microsoft.com"
REGISTRIES_CONF

echo ""
echo "Setting up devcontainer (repo-specific tooling)..."
if [[ -x "$DEVCONTAINER_DIR/setup-devcontainer.sh" ]]; then
  "$DEVCONTAINER_DIR/setup-devcontainer.sh"
else
  echo "  No setup-devcontainer.sh found, skipping"
fi

echo "Running devcontainer verification tests..."
echo ""

# --- Verification Tests ---

if ! docker --version 2>&1 | grep -qi 'podman'; then
  fail "docker CLI is not Podman (got: $(docker --version 2>&1))"
elif sudo -n docker run --rm docker.io/library/hello-world &>/dev/null; then
  pass "Rootful Podman is working (docker → podman)"
else
  echo "  SKIP: Podman not runnable yet (may start via agent script in Coder)"
fi

if pre-commit --version &>/dev/null; then
  pass "Pre-commit is installed"
else
  fail "Pre-commit is not installed"
fi

SAFE_NPM="$HOME/.safe-chain/shims/npm"
if [[ -x "$SAFE_NPM" ]]; then
  TEMP_DIR=$(mktemp -d)
  SAFE_OUTPUT=$(cd "$TEMP_DIR" && "$SAFE_NPM" install safe-chain-test 2>&1 || true)
  rm -rf "$TEMP_DIR"
  if echo "$SAFE_OUTPUT" | grep -qi "safe-chain"; then
    pass "Safe-chain is blocking malicious packages"
  else
    fail "Safe-chain is not blocking (check output: $SAFE_OUTPUT)"
  fi
else
  fail "Safe-chain shims not found at $SAFE_NPM"
fi

if command -v gh &>/dev/null; then
  pass "GitHub CLI is installed"
else
  fail "GitHub CLI is not installed"
fi

SSH_AGENT_OK=false
if [[ -S "${SSH_AUTH_SOCK:-}" ]]; then
  ssh_rc=0
  SSH_ASKPASS='' ssh-add -l &>/dev/null || ssh_rc=$?
  [[ $ssh_rc -ne 2 ]] && SSH_AGENT_OK=true
fi
if $SSH_AGENT_OK; then
  pass "SSH agent reachable ($SSH_AUTH_SOCK)"
elif [[ -f "/etc/coder/ssh-keys/id_ed25519" ]]; then
  pass "SSH key mounted (Coder direct mount)"
elif [[ -n "${GIT_SSH_COMMAND:-}" ]]; then
  pass "GIT_SSH_COMMAND configured"
else
  echo "  SKIP: No SSH key configured"
fi

if command -v claude &>/dev/null; then
  pass "Claude Code CLI is installed"
else
  fail "Claude Code CLI is not installed"
fi

if [[ -x /usr/local/bin/agent-run ]]; then
  agent_run_out=$(/usr/local/bin/agent-run --privileged alpine true 2>&1 || true)
  if echo "$agent_run_out" | grep -q 'forbidden flag'; then
    pass "agent-run wrapper installed and enforcing policy"
  else
    fail "agent-run wrapper installed but not enforcing --privileged rejection"
  fi
else
  fail "agent-run wrapper not installed"
fi

if command -v podman &>/dev/null; then
  graph_driver=$(podman info --format '{{.Store.GraphDriverName}}' 2>/dev/null || echo "unknown")
  if [[ "$graph_driver" == "overlay" ]]; then
    pass "Podman storage driver is overlay"
  else
    echo "  SKIP: Podman graph driver is '$graph_driver' (expected 'overlay')"
  fi
else
  fail "Podman not installed"
fi

echo ""
echo "Results: $PASSED passed, $FAILED failed"

if [[ $FAILED -eq 0 ]]; then
  exit 0
else
  exit 1
fi
