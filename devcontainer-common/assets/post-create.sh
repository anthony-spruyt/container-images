#!/bin/bash
set -euo pipefail

# Usage: devcontainer-post-create [workspace-dir]

WORKSPACE="${1:-.}"
DEVCONTAINER_DIR="$WORKSPACE/.devcontainer"

PASSED=0
FAILED=0
SKIPPED=0
pass() {
  echo "✓ $1"
  PASSED=$((PASSED + 1))
}
fail() {
  echo "✗ $1"
  FAILED=$((FAILED + 1))
}
skip() {
  echo "  SKIP: $1"
  SKIPPED=$((SKIPPED + 1))
}

git config --global --get-all safe.directory 2>/dev/null | grep -xF '*' >/dev/null ||
  git config --global --add safe.directory '*'

sudo mkdir -p /etc/containers/registries.conf.d /etc/containers/containers.conf.d
sudo chmod a+rx /etc/containers /etc/containers/registries.conf.d /etc/containers/containers.conf.d

git ls-files -z '*.sh' | xargs -0 -r chmod +x 2>/dev/null || true

# renovate: datasource=npm depName=@aikidosec/safe-chain
SAFE_CHAIN_VERSION="1.5.24"
SAFE_CHAIN_SHIMS="$HOME/.safe-chain/shims"
# Shims inherited from ~/.bashrc break npm when the global package behind them is gone
shims_real=$(realpath -m "$SAFE_CHAIN_SHIMS")
IFS=: read -ra path_entries <<<"$PATH"
npm_path=""
for entry in "${path_entries[@]}"; do
  [[ "$(realpath -m "$entry" 2>/dev/null)" == "$shims_real" ]] || npm_path+="${npm_path:+:}$entry"
done
npm_prefix=$(PATH="$npm_path" npm prefix -g)
installed_safe_chain=$(jq -r '.version // empty' "$npm_prefix/lib/node_modules/@aikidosec/safe-chain/package.json" 2>/dev/null || true)
if [[ "$installed_safe_chain" == "$SAFE_CHAIN_VERSION" && -x "$npm_prefix/bin/safe-chain" ]]; then
  echo "safe-chain ${SAFE_CHAIN_VERSION} already installed, skipping npm install"
else
  echo "Installing safe-chain ${SAFE_CHAIN_VERSION}..."
  PATH="$npm_path" npm install -g --ignore-scripts "@aikidosec/safe-chain@${SAFE_CHAIN_VERSION}"
fi
safe-chain setup
safe-chain setup-ci
export PATH="$SAFE_CHAIN_SHIMS:$PATH"
# shellcheck disable=SC2016
grep -q 'safe-chain/shims' "$HOME/.bashrc" 2>/dev/null || echo 'export PATH="$HOME/.safe-chain/shims:$PATH"' >>"$HOME/.bashrc"

echo "Installing pre-commit hooks..."
git config --unset-all core.hooksPath 2>/dev/null || true
pre-commit install --install-hooks

export PATH="$HOME/.local/bin:$PATH"
claude_with_timeout() {
  timeout --foreground 120 claude "$@" </dev/null
}
if claude --version &>/dev/null; then
  # Self-update is off where CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC is set
  echo "Updating Claude Code CLI..."
  claude_with_timeout update || echo "WARNING: claude update failed; keeping installed version"
else
  echo "Installing Claude Code CLI..."
  curl -fsSL https://claude.ai/install.sh | bash
fi
# shellcheck disable=SC2016
grep -q 'local/bin' "$HOME/.bashrc" 2>/dev/null || echo 'export PATH="$HOME/.local/bin:$PATH"' >>"$HOME/.bashrc"

if command -v claude &>/dev/null && command -v jq &>/dev/null; then
  WORKSPACE_ABS=$(realpath "$WORKSPACE")
  KNOWN_MARKETPLACES=""
  INSTALLED_PLUGINS=""
  ADDED_REPOS=""
  NEW_PLUGINS=""
  REFRESHED_MARKETPLACES=""
  any_path_exists() {
    local path
    while IFS= read -r path; do
      [[ -n "$path" && -e "$path" ]] && return 0
    done
    return 1
  }
  marketplace_known() {
    local repo="$1"
    grep -qxF -- "$repo" <<<"$ADDED_REPOS" && return 0
    [[ -n "$KNOWN_MARKETPLACES" ]] || KNOWN_MARKETPLACES=$(claude plugins marketplace list --json 2>/dev/null) || KNOWN_MARKETPLACES='[]'
    jq -r --arg r "$repo" '.[] | select(.repo == $r) | .installLocation // empty' <<<"$KNOWN_MARKETPLACES" 2>/dev/null | any_path_exists
  }
  plugin_installed() {
    local plugin="$1" project_scope_counts="$2"
    grep -qxF -- "$plugin" <<<"$NEW_PLUGINS" && return 0
    [[ -n "$INSTALLED_PLUGINS" ]] || INSTALLED_PLUGINS=$(claude plugins list --json 2>/dev/null) || INSTALLED_PLUGINS='[]'
    jq -r --arg p "$plugin" --arg w "$WORKSPACE_ABS" --argjson project "$project_scope_counts" \
      '.[] | select(.id == $p and (.scope == "user" or ($project and .projectPath == $w))) | .installPath // empty' <<<"$INSTALLED_PLUGINS" 2>/dev/null | any_path_exists
  }
  install_plugin() {
    local plugin="$1" marketplace="${1##*@}"
    claude_with_timeout plugins install "$plugin" --scope user && return 0
    # A marketplace clone kept from an earlier run can predate the plugin
    grep -qxF -- "$marketplace" <<<"$REFRESHED_MARKETPLACES" && return 1
    REFRESHED_MARKETPLACES+="$marketplace"$'\n'
    echo "    refreshing marketplace '$marketplace' and retrying"
    claude_with_timeout plugins marketplace update "$marketplace" && claude_with_timeout plugins install "$plugin" --scope user
  }
  bootstrap_claude_plugins() {
    local settings_file="$1" project_scope_counts="$2" marketplaces plugins name repo plugin
    [ -f "$settings_file" ] || return 0
    jq empty "$settings_file" 2>/dev/null || {
      echo "  WARNING: invalid JSON in $settings_file, skipping"
      return 0
    }
    echo "  reading $settings_file"
    marketplaces=$(jq -r '.extraKnownMarketplaces // {} | to_entries[] | select(.key != "claude-plugins-official") | select(.value.source != null and .value.source.repo != null) | "\(.key)\t\(.value.source.repo)"' "$settings_file" 2>/dev/null) || {
      echo "    WARNING: unexpected extraKnownMarketplaces shape in $settings_file, skipping marketplaces"
      marketplaces=""
    }
    if [[ -n "$marketplaces" ]]; then
      while IFS=$'\t' read -r -u 3 name repo; do
        if marketplace_known "$repo"; then
          echo "    marketplace: $name (already added)"
          continue
        fi
        echo "    marketplace: $name ($repo)"
        if claude_with_timeout plugins marketplace add "$repo" --scope user; then
          ADDED_REPOS+="$repo"$'\n'
          REFRESHED_MARKETPLACES+="$name"$'\n'
        else
          echo "    WARNING: failed to add marketplace '$name'"
        fi
      done 3<<<"$marketplaces"
    fi
    plugins=$(jq -r '.enabledPlugins // {} | to_entries[] | select(.value == true or .value == "true") | select(.key | endswith("@claude-plugins-official") | not) | .key' "$settings_file" 2>/dev/null) || {
      echo "    WARNING: unexpected enabledPlugins shape in $settings_file, skipping plugins"
      plugins=""
    }
    [[ -n "$plugins" ]] || return 0
    while IFS= read -r -u 3 plugin; do
      if plugin_installed "$plugin" "$project_scope_counts"; then
        echo "    install: $plugin (already installed)"
        continue
      fi
      echo "    install: $plugin"
      if install_plugin "$plugin"; then
        NEW_PLUGINS+="$plugin"$'\n'
      else
        echo "    WARNING: failed to install '$plugin'"
      fi
    done 3<<<"$plugins"
  }
  echo "Bootstrapping Claude Code plugins..."
  # Settings precedence: user → project → local
  bootstrap_claude_plugins "$HOME/.claude/settings.json" false
  bootstrap_claude_plugins "$WORKSPACE/.claude/settings.json" true
  bootstrap_claude_plugins "$WORKSPACE/.claude/settings.local.json" true
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

if ! docker --version 2>&1 | grep -qi 'podman'; then
  fail "docker CLI is not Podman (got: $(docker --version 2>&1))"
elif docker run --rm docker.io/library/hello-world &>/dev/null; then
  pass "Rootful Podman is working (docker → podman)"
else
  skip "Podman not runnable yet (may start via agent script in Coder)"
fi

if pre-commit --version &>/dev/null; then
  pass "Pre-commit is installed"
else
  fail "Pre-commit is not installed"
fi

SAFE_NPM="$SAFE_CHAIN_SHIMS/npm"
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
  skip "No SSH key configured"
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
    skip "Podman graph driver is '$graph_driver' (expected 'overlay')"
  fi
else
  fail "Podman not installed"
fi

echo ""
echo "Results: $PASSED passed, $FAILED failed, $SKIPPED skipped"

if [[ $FAILED -eq 0 ]]; then
  exit 0
else
  exit 1
fi
