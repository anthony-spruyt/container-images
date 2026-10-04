#!/bin/bash
set -euo pipefail

# Usage: test-post-create.sh [post-create.sh]
# Needs the image's /usr/local/bin/agent-run; run it inside devcontainer-common.
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
markets="$dir/stub-marketplaces.json"
plugins="$dir/stub-plugins.json"
[[ -f "$markets" ]] || echo '[]' >"$markets"
[[ -f "$plugins" ]] || echo '[]' >"$plugins"
case "$2 $3" in
"marketplace list") cat "$markets" ;;
"marketplace add")
  name="${4##*/}"
  mkdir -p "$dir/marketplaces/$name"
  jq --arg n "$name" --arg r "$4" --arg l "$dir/marketplaces/$name" \
    'map(select(.name != $n)) + [{name: $n, source: "github", repo: $r, installLocation: $l}]' "$markets" >"$markets.tmp" && mv "$markets.tmp" "$markets"
  ;;
"list --json") cat "$plugins" ;;
install*)
  mkdir -p "$dir/cache/$3"
  jq --arg p "$3" --arg l "$dir/cache/$3" \
    'map(select(.id != $p)) + [{id: $p, scope: "user", installPath: $l}]' "$plugins" >"$plugins.tmp" && mv "$plugins.tmp" "$plugins"
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
echo "fresh install: OK"

echo "=== second run skips finished work ==="
run
expect_skipped "npm install -g" "safe-chain reinstalled"
expect_skipped "safe-chain setup" "safe-chain setup re-run"
expect_skipped "curl" "Claude Code reinstalled"
expect_skipped "claude update" "working Claude Code CLI updated on every run"
expect_called "pre-commit install --install-hooks" "pre-commit hooks not installed into the workspace"
expect_skipped "claude plugins marketplace add" "marketplace re-added"
expect_skipped "claude plugins install" "plugin reinstalled"
expect_called "docker run" "podman verification skipped"
expect_called "shim-npm install safe-chain-test" "safe-chain verification skipped"
expect_skipped "agent-run" "agent-run resolved from PATH instead of the image's wrapper"
expect_called "devcontainer-podman-config" "per-container podman config skipped"
expect_called "sudo tee /etc/containers/storage.conf" "per-container /etc writes skipped"
[[ $(git config --global --get-all safe.directory | grep -cx '\*') -eq 1 ]] || fail "safe.directory duplicated in ~/.gitconfig"
echo "second run: OK"

echo "=== broken Claude Code CLI is reinstalled ==="
touch "$STUB_CLAUDE_BROKEN"
run
expect_called "curl" "broken Claude Code CLI kept"
rm "$STUB_CLAUDE_BROKEN"
echo "broken claude: OK"

echo "=== empty safe-chain shims are repaired ==="
rm -f "$HOME"/.safe-chain/shims/*
run
expect_called "npm install -g @aikidosec/safe-chain@$version" "empty shims dir treated as installed"
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

echo "=== plugin entry without an install path is reinstalled ==="
jq 'map(.installPath = "")' "$HOME/.claude/plugins/stub-plugins.json" >"$ROOT/plugins.json"
mv "$ROOT/plugins.json" "$HOME/.claude/plugins/stub-plugins.json"
run
expect_called "claude plugins install alpha@plugins-mp" "plugin without install path trusted"
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
run
expect_called "npm install -g @aikidosec/safe-chain@$version" "safe-chain not reinstalled after losing the global package"
echo "reinstall after lost global package: OK"

echo "=== pinned safe-chain bump upgrades ==="
sed "s/^SAFE_CHAIN_VERSION=.*/SAFE_CHAIN_VERSION=\"0.0.1\"/" "$SCRIPT" >"$ROOT/bumped.sh"
run "$ROOT/bumped.sh"
expect_called "npm install -g @aikidosec/safe-chain@0.0.1" "bumped safe-chain not installed"
expect_called "safe-chain setup" "bumped safe-chain not set up"
manifests=("$HOME"/.safe-chain/post-create-shims-*)
[[ ${#manifests[@]} -eq 1 ]] || fail "stale safe-chain shim manifests kept: ${manifests[*]}"
echo "version bump: OK"

echo "=== new plugin installs only the new one ==="
jq '.enabledPlugins["beta@plugins-mp"] = true' "$HOME/.claude/settings.json" >"$ROOT/settings.json"
mv "$ROOT/settings.json" "$HOME/.claude/settings.json"
run
expect_called "claude plugins install beta@plugins-mp" "new plugin not installed"
expect_skipped "claude plugins install alpha@plugins-mp" "existing plugin reinstalled"
echo "new plugin: OK"

echo "post-create idempotency tests passed!"
