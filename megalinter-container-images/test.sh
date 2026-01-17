#!/bin/bash
# Test script for megalinter-container-images custom flavor
# Usage: ./test.sh <image-ref>

set -euo pipefail

IMAGE_REF="${1:?Usage: $0 <image-ref>}"

echo "=== MegaLinter Container-Images Flavor Tests ==="
echo "Image: $IMAGE_REF"
echo ""

# Test 1: Verify all expected linters are available
echo "Test 1: Checking linter availability..."

FAILED=0

check_linter() {
    local name="$1"
    local cmd="$2"
    # shellcheck disable=SC2086 # Word splitting is intentional for command arguments
    if docker run --rm --entrypoint="" "$IMAGE_REF" $cmd >/dev/null 2>&1; then
        echo "  [PASS] $name"
    else
        echo "  [FAIL] $name"
        FAILED=$((FAILED + 1))
    fi
}

# Bash linters (from ci_light base)
check_linter "shellcheck" "shellcheck --version"
check_linter "shfmt" "shfmt --version"

# Dockerfile linter (from ci_light base)
check_linter "hadolint" "hadolint --version"

# YAML linter (from ci_light base)
check_linter "yamllint" "yamllint --version"

# JSON linter (from ci_light base)
check_linter "jsonlint" "jsonlint --version"

# Security linters (from ci_light base)
check_linter "gitleaks" "gitleaks version"
check_linter "secretlint" "secretlint --version"
check_linter "trivy" "trivy --version"

# Added linters (not in ci_light)
check_linter "actionlint" "actionlint --version"
check_linter "markdownlint" "markdownlint --version"
check_linter "lychee" "lychee --version"

echo ""

# Test 2: Verify MegaLinter flavor is set correctly
echo "Test 2: Checking MEGALINTER_FLAVOR environment variable..."
FLAVOR=$(docker run --rm --entrypoint="" "$IMAGE_REF" printenv MEGALINTER_FLAVOR 2>/dev/null || echo "NOT_SET")
if [ "$FLAVOR" = "container-images" ]; then
    echo "  [PASS] MEGALINTER_FLAVOR=$FLAVOR"
else
    echo "  [FAIL] MEGALINTER_FLAVOR=$FLAVOR (expected: container-images)"
    FAILED=$((FAILED + 1))
fi

echo ""

if [ $FAILED -gt 0 ]; then
    echo "=== $FAILED test(s) FAILED ==="
    exit 1
else
    echo "=== All tests passed ==="
fi
