#!/bin/bash
set -euo pipefail

# Usage: test-post-create.sh [post-create.sh]
SCRIPT=$(realpath "${1:-$(dirname "${BASH_SOURCE[0]}")/assets/post-create.sh}")

ROOT=$(mktemp -d)
trap 'rm -rf "$ROOT"' EXIT
export HOME="$ROOT/home"
export STUB_LOG="$ROOT/calls.log"
export STUB_NPM_ROOT="$ROOT/npm-root"
export STUBS="$ROOT/stubs"
export STUB_CLAUDE_BROKEN="$ROOT/claude-broken"
export TMPDIR="$ROOT/tmp"
WORKSPACE="$ROOT/workspace"
mkdir -p "$HOME/.claude" "$STUBS" "$STUB_NPM_ROOT" "$TMPDIR" "$WORKSPACE"
git init -q "$WORKSPACE"

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
stub devcontainer-podman-config </dev/null
stub devcontainer-nexus-config </dev/null
stub pre-commit </dev/null
stub gh </dev/null
stub agent-run <<'EOF'
echo "forbidden flag"
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
install)
  mkdir -p "$STUB_NPM_ROOT/@aikidosec/safe-chain"
  jq -n --arg v "${3##*@}" '{version: $v}' >"$STUB_NPM_ROOT/@aikidosec/safe-chain/package.json"
  ;;
esac
EOF
stub safe-chain <<'EOF'
mkdir -p "$HOME/.safe-chain/shims"
for shim in npm npx; do
  printf '#!/bin/bash\necho "shim-%s $*" >>"$STUB_LOG"\necho "safe-chain blocked"\n' "$shim" >"$HOME/.safe-chain/shims/$shim"
  chmod +x "$HOME/.safe-chain/shims/$shim"
done
EOF
stub curl <<'EOF'
echo 'mkdir -p "$HOME/.local/bin" && cp "$STUBS/claude" "$HOME/.local/bin/claude"'
EOF
stub claude <<'EOF'
if [[ "$1" == --version ]]; then
  [[ -e "$STUB_CLAUDE_BROKEN" ]] && exit 1
  exit 0
fi
dir="$HOME/.claude/plugins"
mkdir -p "$dir"
case "$2" in
marketplace)
  name="${4##*/}"
  file="$dir/known_marketplaces.json"
  [[ -f "$file" ]] || echo '{}' >"$file"
  mkdir -p "$dir/marketplaces/$name"
  jq --arg n "$name" --arg r "$4" --arg l "$dir/marketplaces/$name" \
    '.[$n] = {source: {source: "github", repo: $r}, installLocation: $l}' "$file" >"$file.tmp" && mv "$file.tmp" "$file"
  ;;
install)
  file="$dir/installed_plugins.json"
  [[ -f "$file" ]] || echo '{"version":2,"plugins":{}}' >"$file"
  mkdir -p "$dir/cache/$3"
  jq --arg p "$3" --arg l "$dir/cache/$3" '.plugins[$p] = [{scope: "user", installPath: $l}]' "$file" >"$file.tmp" && mv "$file.tmp" "$file"
  ;;
esac
EOF

cat >"$HOME/.claude/settings.json" <<'JSON'
{
  "extraKnownMarketplaces": {"plugins-mp": {"source": {"source": "github", "repo": "owner/plugins-mp"}}},
  "enabledPlugins": {"alpha@plugins-mp": true}
}
JSON
echo "repos: []" >"$WORKSPACE/.pre-commit-config.yaml"

run() {
  local script="${1:-$SCRIPT}" rc=0
  : >"$STUB_LOG"
  OUT=$(cd "$WORKSPACE" && PATH="$STUBS:$PATH" bash "$script" "$WORKSPACE" 2>&1) || rc=$?
  if [[ $rc -ne 0 ]] || ! grep -q '^Results:' <<<"$OUT"; then
    echo "$OUT"
    fail "script exited $rc before reporting clean results"
  fi
}

skipped_count() {
  grep -oP '^Results:.* \K[0-9]+(?= skipped)' <<<"$OUT"
}

called() {
  local pattern="$1"
  grep -qF -- "$pattern" "$STUB_LOG"
}
expect_called() {
  local pattern="$1" message="$2"
  called "$pattern" || fail "$message"
}
expect_skipped() {
  local pattern="$1" message="$2"
  ! called "$pattern" || fail "$message"
}

version=$(grep -oP '^SAFE_CHAIN_VERSION="\K[^"]+' "$SCRIPT")

echo "=== fresh workspace installs everything ==="
run
expect_called "npm install -g @aikidosec/safe-chain@$version" "safe-chain not installed"
expect_called "safe-chain setup-ci" "safe-chain setup-ci not run"
expect_called "curl" "Claude Code not installed"
expect_called "pre-commit install --install-hooks" "pre-commit hooks not installed"
expect_called "claude plugins marketplace add owner/plugins-mp" "marketplace not added"
expect_called "claude plugins install alpha@plugins-mp" "plugin not installed"
expect_called "docker run" "podman verification skipped on first run"
expect_called "shim-npm install safe-chain-test" "safe-chain verification skipped on first run"
first_run_skipped=$(skipped_count) || fail "results line has no skipped count"
echo "fresh install: OK"

echo "=== second run skips finished work ==="
run
expect_skipped "npm install -g" "safe-chain reinstalled"
expect_skipped "safe-chain setup" "safe-chain setup re-run"
expect_skipped "curl" "Claude Code reinstalled"
expect_called "claude update" "installed Claude Code CLI not updated"
expect_called "pre-commit install --install-hooks" "pre-commit hooks not installed into the workspace"
expect_skipped "claude plugins marketplace add" "marketplace re-added"
expect_skipped "claude plugins install" "plugin reinstalled"
expect_called "docker run" "podman verification skipped after per-container config rewrite"
expect_skipped "shim-npm" "safe-chain verification repeated"
expect_called "devcontainer-podman-config" "per-container podman config skipped"
expect_called "sudo tee /etc/containers/storage.conf" "per-container /etc writes skipped"
second_run_skipped=$(skipped_count) || fail "results line has no skipped count"
((second_run_skipped > first_run_skipped)) || fail "skipped checks not reported ($first_run_skipped then $second_run_skipped)"
[[ $(git config --global --get-all safe.directory | grep -cx '\*') -eq 1 ]] || fail "safe.directory duplicated in ~/.gitconfig"
echo "second run: OK"

echo "=== rebuilt container keeps HOME but must re-verify ==="
rm -rf "${TMPDIR:?}/devcontainer-post-create-$(id -u)"
run
expect_called "docker run" "podman verification skipped in a rebuilt container"
expect_called "shim-npm install safe-chain-test" "safe-chain verification skipped in a rebuilt container"
echo "rebuilt container: OK"

echo "=== broken Claude Code CLI is reinstalled ==="
touch "$STUB_CLAUDE_BROKEN"
run
expect_called "curl" "broken Claude Code CLI kept"
rm "$STUB_CLAUDE_BROKEN"
echo "broken claude: OK"

echo "=== empty safe-chain shims are repaired ==="
rm "$HOME/.safe-chain/shims/npm"
run
expect_called "npm install -g @aikidosec/safe-chain@$version" "empty shims dir treated as installed"
expect_called "shim-npm install safe-chain-test" "repaired safe-chain not verified"
echo "empty shims: OK"

echo "=== any lost safe-chain shim is repaired ==="
rm "$HOME/.safe-chain/shims/npx"
run
expect_called "npm install -g @aikidosec/safe-chain@$version" "missing npx shim treated as installed"
echo "lost shim: OK"

echo "=== lost plugin cache is restored ==="
rm -rf "$HOME/.claude/plugins/cache" "$HOME/.claude/plugins/marketplaces"
run
expect_called "claude plugins marketplace add owner/plugins-mp" "marketplace with missing files trusted"
expect_called "claude plugins install alpha@plugins-mp" "plugin with missing files trusted"
echo "lost cache: OK"

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

echo "=== agent-run is found on PATH, not via env ==="
AGENT_RUN=/nonexistent run
expect_called "agent-run --privileged" "agent-run not resolved from PATH"
echo "agent-run lookup: OK"

echo "=== unwritable stamp dir does not fail a clean run ==="
stamp_dir="$TMPDIR/devcontainer-post-create-$(id -u)"
rm -rf "$stamp_dir" && mkdir -p "$stamp_dir" && chmod 555 "$stamp_dir"
run
chmod 755 "$stamp_dir"
echo "unwritable stamp dir: OK"

echo "=== DEVCONTAINER_VERIFY=1 forces verification ==="
DEVCONTAINER_VERIFY=1 run
expect_called "docker run" "podman verification not forced"
expect_called "shim-npm install safe-chain-test" "safe-chain verification not forced"
echo "forced verification: OK"

echo "=== safe-chain missing from a fresh container ==="
rm -rf "${STUB_NPM_ROOT:?}"/*
run
expect_called "npm install -g @aikidosec/safe-chain@$version" "safe-chain not reinstalled after losing the global package"
echo "reinstall after lost global package: OK"

echo "=== pinned safe-chain bump upgrades ==="
sed "s/^SAFE_CHAIN_VERSION=.*/SAFE_CHAIN_VERSION=\"0.0.1\"/" "$SCRIPT" >"$ROOT/bumped.sh"
run "$ROOT/bumped.sh"
expect_called "npm install -g @aikidosec/safe-chain@0.0.1" "bumped safe-chain not installed"
expect_called "safe-chain setup" "bumped safe-chain not set up"
echo "version bump: OK"

echo "=== new plugin installs only the new one ==="
jq '.enabledPlugins["beta@plugins-mp"] = true' "$HOME/.claude/settings.json" >"$ROOT/settings.json"
mv "$ROOT/settings.json" "$HOME/.claude/settings.json"
run
expect_called "claude plugins install beta@plugins-mp" "new plugin not installed"
expect_skipped "claude plugins install alpha@plugins-mp" "existing plugin reinstalled"
echo "new plugin: OK"

echo "post-create idempotency tests passed!"
