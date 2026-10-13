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
if err=$(run_helper CLAUDE_CODE_MCP_SERVER_NAME=litellm AP_MCP_SESSION_KEY=session-1 "AP_LITELLM_API_KEY=$(printf 'secret-a\nsecret-b')" 2>&1); then
  fail "helper succeeded with a newline in the key"
fi
[[ "$err" != *secret* ]] || fail "newline rejection leaks the key: $err"
if err=$(run_helper CLAUDE_CODE_MCP_SERVER_NAME=other AP_MCP_SESSION_KEY=session-1 AP_LITELLM_API_KEY=llm-1 2>&1); then
  fail "helper succeeded for an unknown server"
fi
[[ "$err" != *session-1* && "$err" != *llm-1* ]] || fail "unknown-server error leaks a key: $err"
echo "OK: ap-mcp-headers"

echo "=== Plugin bootstrap ==="
ROOT=$(mktemp -d)
trap 'rm -rf "$ROOT"' EXIT
export HOME="$ROOT/home"
export STUB_LOG="$ROOT/calls.log"
WORKSPACE="$ROOT/repo"
export STUB_FAIL_INSTALL="$ROOT/fail-install"
export STUB_FAIL_ADD="$ROOT/fail-add"
mkdir -p "$HOME/.local/bin" "$HOME/.claude" "$WORKSPACE/.claude"

cat >"$HOME/.local/bin/claude" <<'STUB'
#!/bin/bash
echo "claude $*" >>"$STUB_LOG"
last="${@: -1}"
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
    [[ -e "$STUB_FAIL_ADD" ]] && exit 1
    mkdir -p "$dir/marketplaces/${last##*/}"
    jq --arg r "$last" --arg l "$dir/marketplaces/${last##*/}" '. + [{repo: $r, installLocation: $l}]' "$markets" >"$markets.tmp" && mv "$markets.tmp" "$markets"
    ;;
  esac
  ;;
"plugins list") cat "$plugins" ;;
"plugins install")
  [[ -e "$STUB_FAIL_INSTALL" ]] && exit 1
  mkdir -p "$dir/cache/$last"
  jq --arg p "$last" --arg l "$dir/cache/$last" '. + [{id: $p, scope: "user", installPath: $l}]' "$plugins" >"$plugins.tmp" && mv "$plugins.tmp" "$plugins"
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

calls() {
  local pattern="$1"
  grep -cF -- "$pattern" "$STUB_LOG" || true
}

: >"$STUB_LOG"
claude-plugins-bootstrap "$WORKSPACE"
[[ $(calls "claude plugins marketplace add --scope user -- owner/plugins-mp") -eq 1 ]] || fail "marketplace not added at user scope"
[[ $(calls "claude plugins install --scope user -- alpha@plugins-mp") -eq 1 ]] || fail "enabled plugin not installed at user scope"
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

reset_stub() {
  rm -rf "$HOME/.claude/plugins" "$STUB_FAIL_INSTALL" "$STUB_FAIL_ADD" "$WORKSPACE/.claude"
  mkdir -p "$WORKSPACE/.claude"
  : >"$STUB_LOG"
}
boot() {
  RC=0
  OUT=$(env "$@" claude-plugins-bootstrap "$WORKSPACE" 2>&1) || RC=$?
}
write_settings() { echo "$1" >"$WORKSPACE/.claude/settings.json"; }
GOOD='{"extraKnownMarketplaces": {"plugins-mp": {"source": {"source": "github", "repo": "owner/plugins-mp"}}}, "enabledPlugins": {"alpha@plugins-mp": true}}'

echo "=== Plugin bootstrap failure modes ==="
reset_stub
write_settings "$GOOD"
touch "$STUB_FAIL_INSTALL"
boot CLAUDE_PLUGINS_STRICT=1
[[ $RC -ne 0 ]] || fail "strict mode exited 0 after a failed plugin install"
boot
[[ $RC -eq 0 ]] || fail "default mode exited $RC after a failed plugin install"
grep -q WARNING <<<"$OUT" || fail "default mode did not warn about the failed install"
echo "failed install: strict fails, default warns: OK"

reset_stub
write_settings "$GOOD"
touch "$STUB_FAIL_ADD"
boot CLAUDE_PLUGINS_STRICT=1
[[ $RC -ne 0 ]] || fail "strict mode exited 0 after a failed marketplace add"
boot
[[ $RC -eq 0 ]] || fail "default mode exited $RC after a failed marketplace add"
echo "failed marketplace add: OK"

reset_stub
write_settings '{not json'
boot CLAUDE_PLUGINS_STRICT=1
[[ $RC -ne 0 ]] || fail "strict mode exited 0 on invalid settings JSON"
boot
[[ $RC -eq 0 ]] || fail "default mode exited $RC on invalid settings JSON"
grep -q WARNING <<<"$OUT" || fail "default mode did not warn about invalid JSON"
echo "invalid JSON: OK"

reset_stub
write_settings '{}'
echo '{"enabledPlugins": {"zeta@plugins-mp": true}}' >"$WORKSPACE/.claude/settings.local.json"
boot CLAUDE_PLUGINS_STRICT=1
[[ $RC -eq 0 ]] || fail "strict mode failed on a clean checkout: $OUT"
[[ $(calls "zeta@plugins-mp") -eq 0 ]] || fail "strict mode read settings.local.json"
boot
[[ $(calls "zeta@plugins-mp") -ge 1 ]] || fail "default mode ignored settings.local.json"
echo "settings.local.json: OK"

reset_stub
write_settings "$GOOD"
boot CLAUDE_PLUGINS_STRICT=1
[[ $RC -eq 0 && $(calls "plugins install --scope user -- alpha@plugins-mp") -eq 1 ]] || fail "strict mode did not install a clean checkout: $OUT"
echo "strict mode on a clean checkout: OK"

reset_stub
write_settings '{
  "extraKnownMarketplaces": {
    "bad1": {"source": {"source": "github", "repo": "-evil/mp"}},
    "bad2": {"source": {"source": "github", "repo": "/tmp/mp"}}
  },
  "enabledPlugins": {"-evil@mp": true, "/abs@mp": true}
}'
boot
[[ $RC -eq 0 ]] || fail "default mode exited $RC on option-like values"
grep -q WARNING <<<"$OUT" || fail "default mode did not warn about option-like values"
[[ $(calls "plugins marketplace add") -eq 0 && $(calls "plugins install") -eq 0 ]] || fail "option-like value passed to claude"
boot CLAUDE_PLUGINS_STRICT=1
[[ $RC -ne 0 ]] || fail "strict mode exited 0 on option-like values"
[[ $(calls "plugins marketplace add") -eq 0 && $(calls "plugins install") -eq 0 ]] || fail "strict mode passed an option-like value to claude"
echo "option-like values rejected: OK"

reset_stub
RC=0
OUT=$(env -i HOME="$HOME" PATH=/nonexistent CLAUDE_PLUGINS_STRICT=1 /bin/bash /usr/local/bin/claude-plugins-bootstrap "$WORKSPACE" 2>&1) || RC=$?
[[ $RC -ne 0 ]] || fail "strict mode exited 0 without jq"
RC=0
OUT=$(env -i HOME="$HOME" PATH=/nonexistent /bin/bash /usr/local/bin/claude-plugins-bootstrap "$WORKSPACE" 2>&1) || RC=$?
[[ $RC -eq 0 ]] || fail "default mode exited $RC without jq"
echo "missing tools: OK"
