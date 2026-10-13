#!/bin/bash
set -euo pipefail

# Usage: claude-plugins-bootstrap <workspace-dir>
# Installs the plugins named by user, project and local Claude Code settings at user scope.
# Identical copies in devcontainer-common/assets and claude-agent-read/assets; claude-agent-read/test.sh compares them.
# CLAUDE_PLUGINS_STRICT=1 (pod mode): any failure exits non-zero and settings.local.json is not read.

WORKSPACE="${1:?Usage: claude-plugins-bootstrap <workspace-dir>}"

export PATH="$HOME/.local/bin:$PATH"
STRICT=false
[[ "${CLAUDE_PLUGINS_STRICT:-}" == "1" ]] && STRICT=true
FAILED=false
claude_with_timeout() {
  timeout --foreground 120 claude "$@" </dev/null
}
# problem <indent> <message>: a warning by default, a recorded failure in strict mode
problem() {
  if $STRICT; then
    echo "$1ERROR: $2" >&2
    FAILED=true
  else
    echo "$1WARNING: $2"
  fi
}
# Values from settings must not parse as options or local paths
unsafe_value() {
  [[ "$1" == -* || "$1" == /* ]]
}

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
    claude_with_timeout plugins install --scope user -- "$plugin" && return 0
    # A marketplace clone kept from an earlier run can predate the plugin
    grep -qxF -- "$marketplace" <<<"$REFRESHED_MARKETPLACES" && return 1
    REFRESHED_MARKETPLACES+="$marketplace"$'\n'
    echo "    refreshing marketplace '$marketplace' and retrying"
    claude_with_timeout plugins marketplace update -- "$marketplace" && claude_with_timeout plugins install --scope user -- "$plugin"
  }
  bootstrap_claude_plugins() {
    local settings_file="$1" project_scope_counts="$2" marketplaces plugins name repo plugin
    [ -f "$settings_file" ] || return 0
    jq empty "$settings_file" 2>/dev/null || {
      problem "  " "invalid JSON in $settings_file, skipping"
      return 0
    }
    echo "  reading $settings_file"
    marketplaces=$(jq -r '.extraKnownMarketplaces // {} | to_entries[] | select(.key != "claude-plugins-official") | select(.value.source != null and .value.source.repo != null) | "\(.key)\t\(.value.source.repo)"' "$settings_file" 2>/dev/null) || {
      problem "    " "unexpected extraKnownMarketplaces shape in $settings_file, skipping marketplaces"
      marketplaces=""
    }
    if [[ -n "$marketplaces" ]]; then
      while IFS=$'\t' read -r -u 3 name repo; do
        if unsafe_value "$repo"; then
          problem "    " "marketplace '$name' skipped: value starts with '-' or '/'"
          continue
        fi
        if marketplace_known "$repo"; then
          echo "    marketplace: $name (already added)"
          continue
        fi
        echo "    marketplace: $name ($repo)"
        if claude_with_timeout plugins marketplace add --scope user -- "$repo"; then
          ADDED_REPOS+="$repo"$'\n'
          REFRESHED_MARKETPLACES+="$name"$'\n'
        else
          problem "    " "failed to add marketplace '$name'"
        fi
      done 3<<<"$marketplaces"
    fi
    plugins=$(jq -r '.enabledPlugins // {} | to_entries[] | select(.value == true or .value == "true") | select(.key | endswith("@claude-plugins-official") | not) | .key' "$settings_file" 2>/dev/null) || {
      problem "    " "unexpected enabledPlugins shape in $settings_file, skipping plugins"
      plugins=""
    }
    [[ -n "$plugins" ]] || return 0
    while IFS= read -r -u 3 plugin; do
      if unsafe_value "$plugin"; then
        problem "    " "plugin '$plugin' skipped: value starts with '-' or '/'"
        continue
      fi
      if plugin_installed "$plugin" "$project_scope_counts"; then
        echo "    install: $plugin (already installed)"
        continue
      fi
      echo "    install: $plugin"
      if install_plugin "$plugin"; then
        NEW_PLUGINS+="$plugin"$'\n'
      else
        problem "    " "failed to install '$plugin'"
      fi
    done 3<<<"$plugins"
  }
  echo "Bootstrapping Claude Code plugins..."
  # Settings precedence: user → project → local
  bootstrap_claude_plugins "$HOME/.claude/settings.json" false
  bootstrap_claude_plugins "$WORKSPACE/.claude/settings.json" true
  $STRICT || bootstrap_claude_plugins "$WORKSPACE/.claude/settings.local.json" true
  ! $FAILED || exit 1
elif $STRICT; then
  echo "ERROR: claude and jq are required" >&2
  exit 1
fi
