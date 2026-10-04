#!/bin/bash
set -euo pipefail

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

git config --global --add safe.directory '*'

sudo mkdir -p /etc/containers/registries.conf.d /etc/containers/containers.conf.d
sudo chmod a+rx /etc/containers /etc/containers/registries.conf.d /etc/containers/containers.conf.d

git ls-files -z '*.sh' | xargs -0 -r chmod +x 2>/dev/null || true

# renovate: datasource=npm depName=@aikidosec/safe-chain
SAFE_CHAIN_VERSION="1.5.21"
installed_safe_chain=$(jq -r '.version // empty' "$(npm root -g)/@aikidosec/safe-chain/package.json" 2>/dev/null || true)
if [[ "$installed_safe_chain" == "$SAFE_CHAIN_VERSION" && -d "$HOME/.safe-chain/shims" ]]; then
  echo "safe-chain ${SAFE_CHAIN_VERSION} already installed, skipping"
else
  echo "Installing safe-chain ${SAFE_CHAIN_VERSION}..."
  npm install -g "@aikidosec/safe-chain@${SAFE_CHAIN_VERSION}"
  safe-chain setup
  safe-chain setup-ci
fi
export PATH="$HOME/.safe-chain/shims:$PATH"
# shellcheck disable=SC2016
grep -q 'safe-chain/shims' "$HOME/.bashrc" 2>/dev/null || echo 'export PATH="$HOME/.safe-chain/shims:$PATH"' >>"$HOME/.bashrc"

echo "Installing pre-commit hooks..."
git config --unset-all core.hooksPath 2>/dev/null || true
precommit_stamp=""
if config_sum=$(sha256sum .pre-commit-config.yaml 2>/dev/null); then
  precommit_stamp="${PRE_COMMIT_HOME:-${XDG_CACHE_HOME:-$HOME/.cache}/pre-commit}/.hook-envs-${config_sum%% *}"
fi
if [[ -n "$precommit_stamp" && -e "$precommit_stamp" ]]; then
  pre-commit install
else
  pre-commit install --install-hooks
  if [[ -n "$precommit_stamp" ]]; then
    mkdir -p "$(dirname "$precommit_stamp")"
    touch "$precommit_stamp"
  fi
fi

if [[ -x "$HOME/.local/bin/claude" ]]; then
  echo "Claude Code CLI already installed, skipping"
else
  echo "Installing Claude Code CLI..."
  curl -fsSL https://claude.ai/install.sh | bash
fi
export PATH="$HOME/.local/bin:$PATH"
# shellcheck disable=SC2016
grep -q 'local/bin' "$HOME/.bashrc" 2>/dev/null || echo 'export PATH="$HOME/.local/bin:$PATH"' >>"$HOME/.bashrc"

if command -v claude &>/dev/null && command -v jq &>/dev/null; then
  marketplace_known() {
    jq -e --arg n "$1" 'has($n)' "$HOME/.claude/plugins/known_marketplaces.json" &>/dev/null
  }
  plugin_installed() {
    jq -e --arg p "$1" '(.plugins[$p] // []) | any(.scope == "user")' "$HOME/.claude/plugins/installed_plugins.json" &>/dev/null
  }
  bootstrap_claude_plugins() {
    local settings_file="$1"
    [ -f "$settings_file" ] || return 0
    jq empty "$settings_file" 2>/dev/null || {
      echo "  WARNING: invalid JSON in $settings_file, skipping"
      return 0
    }
    echo "  reading $settings_file"
    jq -r '.extraKnownMarketplaces // {} | to_entries[] | select(.key != "claude-plugins-official") | select(.value.source != null and .value.source.repo != null) | "\(.key)\t\(.value.source.repo)"' \
      "$settings_file" 2>/dev/null | while IFS="$(printf '\t')" read -r name repo; do
      if marketplace_known "$name"; then
        echo "    marketplace: $name (already added)"
        continue
      fi
      echo "    marketplace: $name ($repo)"
      claude plugins marketplace add "$repo" --scope user ||
        echo "    WARNING: failed to add marketplace '$name'"
    done
    jq -r '.enabledPlugins // {} | to_entries[] | select(.value == true or .value == "true") | select(.key | endswith("@claude-plugins-official") | not) | .key' \
      "$settings_file" 2>/dev/null | while IFS= read -r plugin; do
      if plugin_installed "$plugin"; then
        echo "    install: $plugin (already installed)"
        continue
      fi
      echo "    install: $plugin"
      claude plugins install "$plugin" --scope user ||
        echo "    WARNING: failed to install '$plugin'"
    done
  }
  echo "Bootstrapping Claude Code plugins..."
  # Settings precedence: user → project → local
  bootstrap_claude_plugins "$HOME/.claude/settings.json"
  bootstrap_claude_plugins "$WORKSPACE/.claude/settings.json"
  bootstrap_claude_plugins "$WORKSPACE/.claude/settings.local.json"
fi

# Podman runs rootful (see /usr/local/bin/podman), so config lives in /etc.
sudo mkdir -p /var/lib/containers
if [ -b /dev/containers-disk ]; then
  if ! sudo blkid /dev/containers-disk >/dev/null 2>&1; then
    sudo mkfs.ext4 -q -L containers /dev/containers-disk
  fi
  sudo mountpoint -q /var/lib/containers || sudo mount -o noatime /dev/containers-disk /var/lib/containers
fi
sudo chown root:root /var/lib/containers

sudo tee /etc/containers/storage.conf >/dev/null <<'STORAGE_CONF'
[storage]
driver = "overlay"
runroot = "/run/containers/storage"
graphroot = "/var/lib/containers/storage"
STORAGE_CONF

# cgroups are not delegated to nested containers
sudo tee /etc/containers/containers.conf >/dev/null <<'CONTAINERS_CONF'
[containers]
cgroups = "disabled"

[engine]
cgroup_manager = "cgroupfs"
CONTAINERS_CONF

devcontainer-podman-config

sudo tee /etc/containers/registries.conf.d/10-allow-list.conf >/dev/null <<'REGISTRIES_CONF'
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

devcontainer-nexus-config || echo "WARNING: devcontainer-nexus-config failed; podman pulls from upstream"

echo ""
echo "Setting up devcontainer (repo-specific tooling)..."
if [[ -x "$DEVCONTAINER_DIR/setup-devcontainer.sh" ]]; then
  "$DEVCONTAINER_DIR/setup-devcontainer.sh"
else
  echo "  No setup-devcontainer.sh found, skipping"
fi

echo "Running devcontainer verification tests..."
echo ""

VERIFIED_STAMP="$HOME/.cache/devcontainer-post-create/verified-safe-chain-${SAFE_CHAIN_VERSION}"
RUN_SLOW_CHECKS=true
if [[ -e "$VERIFIED_STAMP" && "${DEVCONTAINER_VERIFY:-}" != 1 ]]; then
  RUN_SLOW_CHECKS=false
fi
SLOW_CHECKS_PASSED=true

if ! docker --version 2>&1 | grep -qi 'podman'; then
  fail "docker CLI is not Podman (got: $(docker --version 2>&1))"
elif ! $RUN_SLOW_CHECKS; then
  echo "  SKIP: Podman hello-world verified earlier (DEVCONTAINER_VERIFY=1 to force)"
elif docker run --rm docker.io/library/hello-world &>/dev/null; then
  pass "Rootful Podman is working (docker → podman)"
else
  echo "  SKIP: Podman not runnable yet (may start via agent script in Coder)"
  SLOW_CHECKS_PASSED=false
fi

if pre-commit --version &>/dev/null; then
  pass "Pre-commit is installed"
else
  fail "Pre-commit is not installed"
fi

SAFE_NPM="$HOME/.safe-chain/shims/npm"
if [[ -x "$SAFE_NPM" ]] && ! $RUN_SLOW_CHECKS; then
  echo "  SKIP: Safe-chain blocking test verified earlier (DEVCONTAINER_VERIFY=1 to force)"
elif [[ -x "$SAFE_NPM" ]]; then
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
  if $RUN_SLOW_CHECKS && $SLOW_CHECKS_PASSED; then
    mkdir -p "$(dirname "$VERIFIED_STAMP")"
    touch "$VERIFIED_STAMP"
  fi
  exit 0
else
  exit 1
fi
