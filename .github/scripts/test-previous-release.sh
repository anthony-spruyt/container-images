#!/bin/bash
set -euo pipefail

# Test script for get_previous_release function
# Uses fixture data to mock gh release list output

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FIXTURES_DIR="$SCRIPT_DIR/test-fixtures"

# Extract get_previous_release function from create-release.sh
eval "$(sed -n '/^get_previous_release()/,/^}/p' "$SCRIPT_DIR/create-release.sh")"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Testing get_previous_release()"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

passed=0
failed=0

# Mock gh command to return fixture data
# Usage: set GH_FIXTURE before calling get_previous_release
gh() {
  if [[ "$1" == "release" && "$2" == "list" ]]; then
    cat "$GH_FIXTURE"
  else
    command gh "$@"
  fi
}
export -f gh

run_test() {
  local name="$1"
  local fixture="$2"
  local image="$3"
  local current_tag="$4"
  local expected="$5"

  echo ""
  echo "Test: $name"
  GH_FIXTURE="$FIXTURES_DIR/$fixture"
  export GH_FIXTURE

  result=$(get_previous_release "$image" "$current_tag")

  if [ "$result" = "$expected" ]; then
    echo "  ✅ Passed (got: '$result')"
    passed=$((passed + 1))
  else
    echo "  ❌ Failed"
    echo "     Expected: '$expected'"
    echo "     Got:      '$result'"
    failed=$((failed + 1))
  fi
}

# Test 1: Find previous release in mixed list
run_test "Find previous in mixed releases" \
  "releases-mixed.json" \
  "gastown-dev" \
  "1.2.10" \
  "gastown-dev-1.2.9"

# Test 2: Find previous when current has rebuild suffix
run_test "Skip rebuild suffixes of current version" \
  "releases-with-rebuild.json" \
  "myimage" \
  "1.0.0" \
  "myimage-0.9.0"

# Test 3: No previous release (initial)
run_test "Initial release returns empty" \
  "releases-single.json" \
  "newimage" \
  "1.0.0" \
  ""

# Test 4: Different image in mixed list
run_test "Find megalinter release in mixed list" \
  "releases-mixed.json" \
  "megalinter-xfg" \
  "v1.0.5" \
  ""

# Test 5: Find previous for megalinter-claude-config
run_test "Find megalinter-claude-config (only one exists)" \
  "releases-mixed.json" \
  "megalinter-claude-config" \
  "v1.0.6" \
  ""

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Previous Release Test Summary: $passed passed, $failed failed"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ $failed -gt 0 ]; then
  echo "::error::$failed test(s) failed"
  exit 1
fi

echo "✅ All tests passed"
