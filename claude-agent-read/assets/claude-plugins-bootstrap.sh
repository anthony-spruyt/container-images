#!/bin/bash
set -euo pipefail

# Usage: claude-plugins-bootstrap <workspace-dir>
# Installs the plugins named by user, project and local Claude Code settings at user scope.
# claude-agent-read/assets/claude-plugins-bootstrap.sh is a copy of this file; keep them equal.

WORKSPACE="${1:?Usage: claude-plugins-bootstrap <workspace-dir>}"

export PATH="$HOME/.local/bin:$PATH"
claude_with_timeout() {
  timeout --foreground 120 claude "$@" </dev/null
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
