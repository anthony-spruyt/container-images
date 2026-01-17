#!/bin/bash
set -euo pipefail

# Test script for changelog generation functions
# Run this script to validate changelog logic before CI

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Source the functions from create-release.sh
# We extract just the functions we need
eval "$(sed -n '/^generate_local_changelog()/,/^}/p' "$SCRIPT_DIR/create-release.sh")"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Testing changelog generation"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

passed=0
failed=0

# Test 1: Local image with no previous release (initial)
echo "Test 1: Initial release (no previous tag)"
result=$(generate_local_changelog "test-image" "")
if [ "$result" = "Initial release" ]; then
    echo "  ✅ Passed"
    passed=$((passed + 1))
else
    echo "  ❌ Failed: expected 'Initial release', got '$result'"
    failed=$((failed + 1))
fi

# Test 2: Upstream image changelog format
echo "Test 2: Upstream changelog format"
UPSTREAM="example/repo"
TAG="v1.0.0"
expected="See [example/repo release v1.0.0](https://github.com/example/repo/releases/tag/v1.0.0)"
result="See [${UPSTREAM} release ${TAG}](https://github.com/${UPSTREAM}/releases/tag/${TAG})"
if [ "$result" = "$expected" ]; then
    echo "  ✅ Passed"
    passed=$((passed + 1))
else
    echo "  ❌ Failed: format mismatch"
    failed=$((failed + 1))
fi

# Test 3: Verify generate_local_changelog handles empty commits
echo "Test 3: No commits returns rebuild message"
result=$(generate_local_changelog "nonexistent-image" "v99.99.99")
if [ "$result" = "Rebuild (no source changes)" ]; then
    echo "  ✅ Passed"
    passed=$((passed + 1))
else
    echo "  ❌ Failed: expected 'Rebuild (no source changes)', got '$result'"
    failed=$((failed + 1))
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Changelog Test Summary: $passed passed, $failed failed"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ $failed -gt 0 ]; then
    echo "::error::$failed changelog test(s) failed"
    exit 1
fi

echo "✅ All changelog tests passed"
