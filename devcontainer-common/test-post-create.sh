#!/bin/bash
set -euo pipefail

# Usage: test-post-create.sh [post-create.sh]
# Needs the image's /usr/local/bin/agent-run; run it inside devcontainer-common.
SCRIPT=$(realpath "${1:-$(dirname "${BASH_SOURCE[0]}")/assets/post-create.sh}")

ROOT=$(mktemp -d)
trap 'rm -rf "$ROOT"' EXIT
export HOME="$ROOT/home"
export STUB_LOG="$ROOT/calls.log"
export STUB_NPM_PREFIX="$ROOT/npm-prefix"
export STUB_NPM_ROOT="$STUB_NPM_PREFIX/lib/node_modules"
export STUBS="$ROOT/stubs"
export STUB_CLAUDE_BROKEN="$ROOT/claude-broken"
export STUB_CATALOG="$ROOT/catalog"
export STUB_SRC="$ROOT/stub-src"
export TMPDIR="$ROOT/tmp"
WORKSPACE="$ROOT/workspace"
mkdir -p "$HOME/.claude" "$STUBS" "$STUB_SRC" "$STUB_NPM_PREFIX/bin" "$STUB_NPM_ROOT" "$TMPDIR" "$WORKSPACE"
git init -q "$WORKSPACE"
printf '%s\n' alpha beta >"$STUB_CATALOG"

fail() {
  echo "FAIL: $1"
  echo "--- calls ---"
  cat "$STUB_LOG"
  exit 1
}

stub() {
  local name="$1"
  {
    printf "#!/bin/bash\necho \"%s \$*\" >>\"\$STUB_LOG\"\n" "$name"
    cat
  } >"$STUBS/$name"
  chmod +x "$STUBS/$name"
}

stub sudo </dev/null
stub timeout <<'EOF'
[[ "$1" == --foreground ]] && shift
shift
exec "$@"
EOF
stub devcontainer-podman-config </dev/null
stub devcontainer-nexus-config </dev/null
stub pre-commit </dev/null
stub gh </dev/null
stub agent-run <<'EOF'
echo "running $*"
EOF
stub docker <<'EOF'
[[ "$1" == --version ]] && echo "podman version 5.0.0"
exit 0
EOF
stub podman <<'EOF'
echo overlay
EOF
stub npm <<'EOF'
case "$1" in
root) echo "$STUB_NPM_ROOT" ;;
prefix) echo "$STUB_NPM_PREFIX" ;;
install)
  cp "$STUB_SRC/safe-chain" "$STUB_NPM_PREFIX/bin/safe-chain"
  mkdir -p "$STUB_NPM_ROOT/@aikidosec/safe-chain"
  jq -n --arg v "${4##*@}" '{version: $v}' >"$STUB_NPM_ROOT/@aikidosec/safe-chain/package.json"
  ;;
esac
EOF
stub safe-chain <<'EOF'
case "$1" in
setup)
  grep -q init-posix "$HOME/.bashrc" 2>/dev/null ||
    echo 'source ~/.safe-chain/scripts/init-posix.sh # Safe-chain' >>"$HOME/.bashrc"
  ;;
setup-ci)
  mkdir -p "$HOME/.safe-chain/shims"
  for shim in npm npx; do
    printf '#!/bin/bash\necho "shim-%s $*" >>"$STUB_LOG"\necho "safe-chain blocked"\n' "$shim" >"$HOME/.safe-chain/shims/$shim"
    chmod +x "$HOME/.safe-chain/shims/$shim"
  done
  ;;
esac
EOF
mv "$STUBS/safe-chain" "$STUB_SRC/safe-chain"
stub curl <<'EOF'
echo 'mkdir -p "$HOME/.local/bin" && cp "$STUB_SRC/claude" "$HOME/.local/bin/claude"'
EOF
stub claude <<'EOF'
if [[ "$1" == --version ]]; then
  [[ -e "$STUB_CLAUDE_BROKEN" ]] && exit 1
  exit 0
fi
dir="$HOME/.claude/plugins"
mkdir -p "$dir"
markets="$dir/stub-marketplaces.json"
plugins="$dir/stub-plugins.json"
[[ -f "$markets" ]] || echo '[]' >"$markets"
[[ -f "$plugins" ]] || echo '[]' >"$plugins"
case "$2 $3" in
"marketplace list") cat "$markets" ;;
"marketplace add")
  name="${4##*/}"
  mkdir -p "$dir/marketplaces/$name"
  cp "$STUB_CATALOG" "$dir/marketplaces/$name/catalog"
  jq --arg n "$name" --arg r "$4" --arg l "$dir/marketplaces/$name" \
    'map(select(.name != $n)) + [{name: $n, source: "github", repo: $r, installLocation: $l}]' "$markets" >"$markets.tmp" && mv "$markets.tmp" "$markets"
  ;;
"marketplace update") cp "$STUB_CATALOG" "$dir/marketplaces/$4/catalog" ;;
"list --json") cat "$plugins" ;;
install*)
  grep -qx "${3%@*}" "$dir/marketplaces/${3##*@}/catalog" 2>/dev/null || {
    echo "plugin $3 not found in marketplace" >&2
    exit 1
  }
  mkdir -p "$dir/cache/$3"
  jq --arg p "$3" --arg l "$dir/cache/$3" \
    'map(select(.id != $p)) + [{id: $p, scope: "user", installPath: $l}]' "$plugins" >"$plugins.tmp" && mv "$plugins.tmp" "$plugins"
  ;;
esac
EOF
mv "$STUBS/claude" "$STUB_SRC/claude"
# Shadows any host claude until the stubbed installer puts one in ~/.local/bin
stub claude <<'EOF'
exit 127
EOF

cat >"$HOME/.claude/settings.json" <<'JSON'
{
  "extraKnownMarketplaces": {
    "plugins-mp": {"source": {"source": "github", "repo": "owner/plugins-mp"}},
    "plugins-mp-dup": {"source": {"source": "github", "repo": "owner/plugins-mp"}}
  },
  "enabledPlugins": {"alpha@plugins-mp": true}
}
JSON
mkdir -p "$WORKSPACE/.claude"
echo '{}' >"$WORKSPACE/.claude/settings.json"
echo "repos: []" >"$WORKSPACE/.pre-commit-config.yaml"

run() {
  local script="${1:-$SCRIPT}" rc=0
  : >"$STUB_LOG"
  OUT=$(cd "$WORKSPACE" && PATH="${EXTRA_PATH:+$EXTRA_PATH:}$STUBS:$STUB_NPM_PREFIX/bin:$PATH" bash "$script" "$WORKSPACE" 2>&1) || rc=$?
  if [[ $rc -ne 0 ]] || ! grep -q '^Results:' <<<"$OUT"; then
    echo "$OUT"
    fail "script exited $rc before reporting clean results"
  fi
}

called() {
  local pattern="$1"
  grep -qF -- "$pattern" "$STUB_LOG"
}
expect_called() {
  local pattern="$1" message="$2"
  called "$pattern" || fail "$message"
}
call_count() {
  local pattern="$1"
  awk -v p="$pattern" 'index($0, p) == 1' "$STUB_LOG" | wc -l
}
expect_skipped() {
  local pattern="$1" message="$2"
  ! called "$pattern" || fail "$message"
}

version=$(grep -oP '^SAFE_CHAIN_VERSION="\K[^"]+' "$SCRIPT")
INSTALL_ALPHA="claude plugins install alpha@plugins-mp"

echo "=== fresh workspace installs everything ==="
run
expect_called "npm install -g --ignore-scripts @aikidosec/safe-chain@$version" "safe-chain not installed"
expect_called "safe-chain setup-ci" "safe-chain setup-ci not run"
expect_called "curl" "Claude Code not installed"
expect_called "pre-commit install --install-hooks" "pre-commit hooks not installed"
expect_called "claude plugins marketplace add owner/plugins-mp" "marketplace not added"
expect_called "timeout --foreground 120 claude plugins marketplace add" "marketplace add has no timeout"
expect_called "timeout --foreground 120 claude plugins install alpha@plugins-mp" "plugin install has no timeout"
[[ $(call_count "claude plugins marketplace add owner/plugins-mp") -eq 1 ]] || fail "marketplace shared by two settings keys added twice"
[[ $(call_count "claude plugins marketplace list --json") -eq 1 ]] || fail "marketplace list re-queried after an add"
expect_called "$INSTALL_ALPHA" "plugin not installed"
expect_called "docker run" "podman verification skipped on first run"
expect_called "shim-npm install safe-chain-test" "safe-chain verification skipped on first run"
echo "fresh install: OK"

echo "=== second run skips finished work ==="
run
expect_skipped "npm install -g" "safe-chain reinstalled"
expect_called "safe-chain setup-ci" "safe-chain shims not refreshed"
expect_skipped "curl" "Claude Code reinstalled"
expect_called "timeout --foreground 120 claude update" "installed Claude Code CLI not updated under a timeout"
expect_skipped "npm root" "npm started twice to check safe-chain"
expect_called "pre-commit install --install-hooks" "pre-commit hooks not installed into the workspace"
expect_skipped "claude plugins marketplace add" "marketplace re-added"
expect_skipped "claude plugins install" "plugin reinstalled"
[[ $(call_count "claude plugins list --json") -eq 1 ]] || fail "plugin list queried for a settings file with no plugins"
[[ $(call_count "claude plugins marketplace list --json") -eq 1 ]] || fail "marketplace list queried for a settings file with no marketplaces"
expect_called "docker run" "podman verification skipped"
expect_called "shim-npm install safe-chain-test" "safe-chain verification skipped"
expect_skipped "agent-run" "agent-run resolved from PATH instead of the image's wrapper"
expect_called "devcontainer-podman-config" "per-container podman config skipped"
expect_called "sudo tee /etc/containers/storage.conf" "per-container /etc writes skipped"
[[ $(git config --global --get-all safe.directory | grep -cx '\*') -eq 1 ]] || fail "safe.directory duplicated in ~/.gitconfig"
echo "second run: OK"

echo "=== reset ~/.bashrc gets safe-chain shell integration back ==="
sed -i '/init-posix/d' "$HOME/.bashrc"
run
grep -q init-posix "$HOME/.bashrc" || fail "safe-chain shell integration not restored"
echo "bashrc reset: OK"

echo "=== settings file with an unexpected shape is skipped ==="
echo '{"extraKnownMarketplaces": {"x": {"source": "github"}}, "enabledPlugins": []}' >"$WORKSPACE/.claude/settings.json"
run
grep -q "WARNING" <<<"$OUT" || fail "unexpected settings shape not reported"
expect_called "docker run" "post-create stopped at an unexpected settings shape"
echo '{}' >"$WORKSPACE/.claude/settings.json"
echo "bad settings shape: OK"

echo "=== lost safe-chain command is reinstalled ==="
rm "$STUB_NPM_PREFIX/bin/safe-chain"
run
expect_called "npm install -g --ignore-scripts @aikidosec/safe-chain@$version" "safe-chain package trusted without its command"
echo "lost safe-chain command: OK"

echo "=== claude installed outside ~/.local/bin is updated, not reinstalled ==="
mkdir -p "$ROOT/other-bin"
mv "$HOME/.local/bin/claude" "$ROOT/other-bin/claude"
EXTRA_PATH="$ROOT/other-bin" run
expect_skipped "curl" "claude on PATH reinstalled"
expect_called "claude update" "claude on PATH not updated"
mv "$ROOT/other-bin/claude" "$HOME/.local/bin/claude"
echo "claude elsewhere: OK"

echo "=== project-scope install for this workspace counts ==="
mkdir -p "$ROOT/delta"
jq --arg w "$WORKSPACE" --arg l "$ROOT/delta" '. + [{id: "delta@plugins-mp", scope: "project", projectPath: $w, installPath: $l}]' \
  "$HOME/.claude/plugins/stub-plugins.json" >"$ROOT/plugins.json"
mv "$ROOT/plugins.json" "$HOME/.claude/plugins/stub-plugins.json"
echo '{"enabledPlugins": {"delta@plugins-mp": true}}' >"$WORKSPACE/.claude/settings.json"
run
expect_skipped "claude plugins install delta@plugins-mp" "project-scope plugin reinstalled at user scope"
[[ $(call_count "claude plugins list --json") -eq 1 ]] || fail "plugin list queried once per settings file"
jq '.enabledPlugins["delta@plugins-mp"] = true' "$HOME/.claude/settings.json" >"$ROOT/settings.json"
mv "$ROOT/settings.json" "$HOME/.claude/settings.json"
run
expect_called "claude plugins install delta@plugins-mp" "project-scope install trusted for user settings"
jq '.enabledPlugins |= del(.["delta@plugins-mp"])' "$HOME/.claude/settings.json" >"$ROOT/settings.json"
mv "$ROOT/settings.json" "$HOME/.claude/settings.json"
echo '{}' >"$WORKSPACE/.claude/settings.json"
echo "project scope: OK"

echo "=== plugin published after the marketplace was cloned ==="
jq '.enabledPlugins["gamma@plugins-mp"] = true | .enabledPlugins["omega@plugins-mp"] = true' "$HOME/.claude/settings.json" >"$ROOT/settings.json"
mv "$ROOT/settings.json" "$HOME/.claude/settings.json"
run
[[ $(call_count "claude plugins marketplace update plugins-mp") -eq 1 ]] || fail "marketplace refreshed more than once in a run"
echo gamma >>"$STUB_CATALOG"
run
expect_called "timeout --foreground 120 claude plugins marketplace update plugins-mp" "stale marketplace not refreshed under a timeout"
jq -e 'any(.[]; .id == "gamma@plugins-mp")' "$HOME/.claude/plugins/stub-plugins.json" >/dev/null || fail "newly published plugin not installed"
rm -rf "$HOME/.claude/plugins/marketplaces"
run
expect_skipped "claude plugins marketplace update" "marketplace refreshed right after it was cloned"
jq '.enabledPlugins |= del(.["omega@plugins-mp"])' "$HOME/.claude/settings.json" >"$ROOT/settings.json"
mv "$ROOT/settings.json" "$HOME/.claude/settings.json"
echo "stale marketplace: OK"

echo "=== broken Claude Code CLI is reinstalled ==="
touch "$STUB_CLAUDE_BROKEN"
run
expect_called "curl" "broken Claude Code CLI kept"
rm "$STUB_CLAUDE_BROKEN"
echo "broken claude: OK"

echo "=== lost safe-chain shims are restored without reinstalling ==="
rm -f "$HOME"/.safe-chain/shims/*
run
[[ -x "$HOME/.safe-chain/shims/npm" && -x "$HOME/.safe-chain/shims/npx" ]] || fail "lost shims not restored"
expect_skipped "npm install -g" "safe-chain reinstalled to restore shims"
echo "lost shims: OK"

echo "=== lost plugin cache is restored ==="
rm -rf "$HOME/.claude/plugins/cache" "$HOME/.claude/plugins/marketplaces"
run
expect_called "claude plugins marketplace add owner/plugins-mp" "marketplace with missing files trusted"
expect_called "$INSTALL_ALPHA" "plugin with missing files trusted"
echo "lost cache: OK"

echo "=== plugin entry without an install path is reinstalled ==="
jq 'map(.installPath = "")' "$HOME/.claude/plugins/stub-plugins.json" >"$ROOT/plugins.json"
mv "$ROOT/plugins.json" "$HOME/.claude/plugins/stub-plugins.json"
run
expect_called "$INSTALL_ALPHA" "plugin without install path trusted"
echo "pathless plugin: OK"

echo "=== marketplace found by repo when settings key differs ==="
jq '.extraKnownMarketplaces["alias"] = {source: {source: "github", repo: "owner/other-mp"}}' "$HOME/.claude/settings.json" >"$ROOT/settings.json"
mv "$ROOT/settings.json" "$HOME/.claude/settings.json"
run
expect_called "claude plugins marketplace add owner/other-mp" "aliased marketplace not added"
run
expect_skipped "claude plugins marketplace add" "aliased marketplace re-added"
echo "aliased marketplace: OK"

echo "=== marketplace repo change in settings is added ==="
cp "$HOME/.claude/settings.json" "$ROOT/settings.orig.json"
jq '.extraKnownMarketplaces["plugins-mp"].source.repo = "owner/fork-mp"' "$ROOT/settings.orig.json" >"$HOME/.claude/settings.json"
run
expect_called "claude plugins marketplace add owner/fork-mp" "changed marketplace repo trusted by name"
mv "$ROOT/settings.orig.json" "$HOME/.claude/settings.json"
echo "changed marketplace repo: OK"

echo "=== safe-chain missing from a fresh container ==="
rm -rf "${STUB_NPM_ROOT:?}"/*
EXTRA_PATH="$HOME/.safe-chain//shims/" run
expect_skipped "shim-npm root" "npm resolved to a safe-chain shim before reinstall"
expect_skipped "shim-npm install -g" "npm resolved to a safe-chain shim before reinstall"
[[ $(jq -r .version "$STUB_NPM_ROOT/@aikidosec/safe-chain/package.json" 2>/dev/null) == "$version" ]] ||
  fail "safe-chain not reinstalled after losing the global package"
echo "reinstall after lost global package: OK"

echo "=== pinned safe-chain bump upgrades ==="
sed "s/^SAFE_CHAIN_VERSION=.*/SAFE_CHAIN_VERSION=\"0.0.1\"/" "$SCRIPT" >"$ROOT/bumped.sh"
run "$ROOT/bumped.sh"
expect_called "npm install -g --ignore-scripts @aikidosec/safe-chain@0.0.1" "bumped safe-chain not installed"
echo "version bump: OK"

echo "=== new plugin installs only the new one ==="
jq '.enabledPlugins["beta@plugins-mp"] = true' "$HOME/.claude/settings.json" >"$ROOT/settings.json"
mv "$ROOT/settings.json" "$HOME/.claude/settings.json"
run
expect_called "claude plugins install beta@plugins-mp" "new plugin not installed"
expect_skipped "$INSTALL_ALPHA" "existing plugin reinstalled"
echo "new plugin: OK"

echo "post-create idempotency tests passed!"
