#!/bin/bash
set -euo pipefail

# Runs inside the image. The plugin bootstrap is covered in depth by devcontainer-common/test-post-create.sh.

fail() {
  echo "FAIL: $1"
  [[ -f "${STUB_LOG:-}" ]] && cat "$STUB_LOG"
  exit 1
}

echo "=== Managed settings ==="
settings=/etc/claude-code/managed-settings.json
[[ "$(stat -c %U:%a "$settings")" == "root:644" ]] || fail "$settings must be root-owned and not writable by the agent"
jq -e '. == {
  permissions: {
    defaultMode: "bypassPermissions",
    additionalDirectories: ["/workspace/pr"],
    deny: ["Read(//proc/**)"]
  },
  env: {
    DISABLE_AUTOUPDATER: "1",
    CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC: "1"
  }
}' "$settings" >/dev/null || fail "managed settings differ from the expected content"
echo "OK: managed settings"

echo "=== ap-mcp-headers ==="
# An empty PATH proves the script runs on shell builtins only, so a key never reaches an argv.
run_helper() { env -i PATH=/nonexistent "$@" /bin/bash /usr/local/bin/ap-mcp-headers; }
out=$(run_helper CLAUDE_CODE_MCP_SERVER_NAME=agentplatform AP_MCP_SESSION_KEY=session-1 AP_LITELLM_API_KEY=llm-1)
[[ "$out" == '{"Authorization":"Bearer session-1"}' ]] || fail "agentplatform headers: $out"
out=$(run_helper CLAUDE_CODE_MCP_SERVER_NAME=litellm AP_MCP_SESSION_KEY=session-1 AP_LITELLM_API_KEY=llm-1)
[[ "$out" == '{"x-litellm-api-key":"Bearer llm-1"}' ]] || fail "litellm headers: $out"
out=$(env -i PATH=/nonexistent AP_LITELLM_API_KEY=llm-1 /bin/bash /usr/local/bin/ap-mcp-headers litellm)
[[ "$out" == '{"x-litellm-api-key":"Bearer llm-1"}' ]] || fail "server given as argument: $out"
out=$(run_helper CLAUDE_CODE_MCP_SERVER_NAME=litellm 'AP_LITELLM_API_KEY=a"b\c')
[[ "$(jq -r '."x-litellm-api-key"' <<<"$out")" == 'Bearer a"b\c' ]] || fail "quote and backslash not escaped: $out"
if err=$(run_helper CLAUDE_CODE_MCP_SERVER_NAME=litellm AP_MCP_SESSION_KEY=session-1 2>&1); then
  fail "helper succeeded without AP_LITELLM_API_KEY"
fi
[[ "$err" != *session-1* ]] || fail "error output leaks a key"
if run_helper CLAUDE_CODE_MCP_SERVER_NAME=other AP_MCP_SESSION_KEY=session-1 AP_LITELLM_API_KEY=llm-1 >/dev/null 2>&1; then
  fail "helper succeeded for an unknown server"
fi
echo "OK: ap-mcp-headers"

echo "=== Plugin bootstrap ==="
ROOT=$(mktemp -d)
trap 'rm -rf "$ROOT"' EXIT
export HOME="$ROOT/home"
export STUB_LOG="$ROOT/calls.log"
WORKSPACE="$ROOT/repo"
mkdir -p "$HOME/.local/bin" "$HOME/.claude" "$WORKSPACE/.claude"

cat >"$HOME/.local/bin/claude" <<'STUB'
#!/bin/bash
echo "claude $*" >>"$STUB_LOG"
dir="$HOME/.claude/plugins"
mkdir -p "$dir"
markets="$dir/stub-marketplaces.json"
plugins="$dir/stub-plugins.json"
[[ -f "$markets" ]] || echo '[]' >"$markets"
[[ -f "$plugins" ]] || echo '[]' >"$plugins"
case "$1 $2" in
"plugins marketplace")
  case "$3" in
  list) cat "$markets" ;;
  add)
    mkdir -p "$dir/marketplaces/${4##*/}"
    jq --arg r "$4" --arg l "$dir/marketplaces/${4##*/}" '. + [{repo: $r, installLocation: $l}]' "$markets" >"$markets.tmp" && mv "$markets.tmp" "$markets"
    ;;
  esac
  ;;
"plugins list") cat "$plugins" ;;
"plugins install")
  mkdir -p "$dir/cache/$3"
  jq --arg p "$3" --arg l "$dir/cache/$3" '. + [{id: $p, scope: "user", installPath: $l}]' "$plugins" >"$plugins.tmp" && mv "$plugins.tmp" "$plugins"
  ;;
esac
STUB
chmod +x "$HOME/.local/bin/claude"

cat >"$WORKSPACE/.claude/settings.json" <<'JSON'
{
  "extraKnownMarketplaces": {
    "plugins-mp": {"source": {"source": "github", "repo": "owner/plugins-mp"}}
  },
  "enabledPlugins": {"alpha@plugins-mp": true, "beta@plugins-mp": false}
}
JSON

calls() { grep -cF -- "$1" "$STUB_LOG" || true; }

: >"$STUB_LOG"
claude-plugins-bootstrap "$WORKSPACE"
[[ $(calls "claude plugins marketplace add owner/plugins-mp --scope user") -eq 1 ]] || fail "marketplace not added at user scope"
[[ $(calls "claude plugins install alpha@plugins-mp --scope user") -eq 1 ]] || fail "enabled plugin not installed at user scope"
[[ $(calls "beta@plugins-mp") -eq 0 ]] || fail "disabled plugin touched"
echo "fresh bootstrap installs the project plugins: OK"

: >"$STUB_LOG"
claude-plugins-bootstrap "$WORKSPACE"
[[ $(calls "claude plugins marketplace add") -eq 0 ]] || fail "marketplace re-added"
[[ $(calls "claude plugins install") -eq 0 ]] || fail "plugin reinstalled"
echo "second bootstrap changes nothing: OK"

rm -rf "$WORKSPACE/.claude"
: >"$STUB_LOG"
claude-plugins-bootstrap "$WORKSPACE"
[[ $(calls "claude plugins install") -eq 0 ]] || fail "plugin installed without settings"
echo "repo without settings installs nothing: OK"
