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
WORKSPACE="$ROOT/workspace"
mkdir -p "$HOME/.claude" "$STUBS" "$STUB_NPM_ROOT" "$WORKSPACE"
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
printf '#!/bin/bash\necho "shim-npm $*" >>"$STUB_LOG"\necho "safe-chain blocked"\n' >"$HOME/.safe-chain/shims/npm"
chmod +x "$HOME/.safe-chain/shims/npm"
EOF
stub curl <<'EOF'
echo 'mkdir -p "$HOME/.local/bin" && cp "$STUBS/claude" "$HOME/.local/bin/claude"'
EOF
stub claude <<'EOF'
dir="$HOME/.claude/plugins"
mkdir -p "$dir"
case "$2" in
marketplace)
  file="$dir/known_marketplaces.json"
  [[ -f "$file" ]] || echo '{}' >"$file"
  jq --arg n "${4##*/}" '.[$n] = {}' "$file" >"$file.tmp" && mv "$file.tmp" "$file"
  ;;
install)
  file="$dir/installed_plugins.json"
  [[ -f "$file" ]] || echo '{"version":2,"plugins":{}}' >"$file"
  jq --arg p "$3" '.plugins[$p] = [{scope: "user"}]' "$file" >"$file.tmp" && mv "$file.tmp" "$file"
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
  local script="${1:-$SCRIPT}" out
  : >"$STUB_LOG"
  out=$(cd "$WORKSPACE" && PATH="$STUBS:$PATH" bash "$script" "$WORKSPACE" 2>&1) || true
  grep -q '^Results:' <<<"$out" || {
    echo "$out"
    fail "script aborted before the end"
  }
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
expect_skipped "--install-hooks" "pre-commit hook envs rebuilt"
expect_called "pre-commit install" "pre-commit hook not installed into the workspace"
expect_skipped "claude plugins marketplace add" "marketplace re-added"
expect_skipped "claude plugins install" "plugin reinstalled"
expect_skipped "docker run" "podman verification repeated"
expect_skipped "shim-npm" "safe-chain verification repeated"
expect_called "devcontainer-podman-config" "per-container podman config skipped"
expect_called "sudo tee /etc/containers/storage.conf" "per-container /etc writes skipped"
echo "second run: OK"

echo "=== DEVCONTAINER_VERIFY=1 forces verification ==="
DEVCONTAINER_VERIFY=1 run
expect_called "docker run" "podman verification not forced"
expect_called "shim-npm install safe-chain-test" "safe-chain verification not forced"
echo "forced verification: OK"

echo "=== pinned safe-chain bump upgrades ==="
sed "s/^SAFE_CHAIN_VERSION=.*/SAFE_CHAIN_VERSION=\"0.0.1\"/" "$SCRIPT" >"$ROOT/bumped.sh"
run "$ROOT/bumped.sh"
expect_called "npm install -g @aikidosec/safe-chain@0.0.1" "bumped safe-chain not installed"
expect_called "safe-chain setup" "bumped safe-chain not set up"
echo "version bump: OK"

echo "=== safe-chain missing from a fresh container ==="
rm -rf "${STUB_NPM_ROOT:?}"/*
run
expect_called "npm install -g @aikidosec/safe-chain@$version" "safe-chain not reinstalled after losing the global package"
echo "reinstall after lost global package: OK"

echo "=== pre-commit config change rebuilds hook envs ==="
run
echo "repos: [] # changed" >"$WORKSPACE/.pre-commit-config.yaml"
run
expect_called "pre-commit install --install-hooks" "hook envs not rebuilt after config change"
echo "config change: OK"

echo "=== new plugin installs only the new one ==="
jq '.enabledPlugins["beta@plugins-mp"] = true' "$HOME/.claude/settings.json" >"$ROOT/settings.json"
mv "$ROOT/settings.json" "$HOME/.claude/settings.json"
run
expect_called "claude plugins install beta@plugins-mp" "new plugin not installed"
expect_skipped "claude plugins install alpha@plugins-mp" "existing plugin reinstalled"
echo "new plugin: OK"

echo "post-create idempotency tests passed!"
