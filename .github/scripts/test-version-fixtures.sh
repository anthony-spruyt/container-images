#!/bin/bash
set -euo pipefail

# Test script for version handling using test fixtures
# Run this script to validate version/tag generation before CI

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Source the version handling functions
# shellcheck source=.github/scripts/version-handling.sh
source "$SCRIPT_DIR/version-handling.sh"

echo "🔍 Discovering test fixture images..."
test_images=$(find test-images -name metadata.yaml -type f 2>/dev/null | sort || true)

if [ -z "$test_images" ]; then
  echo "::error::No test fixture images found in test-images/"
  exit 1
fi

total=0
passed=0
failed=0

for metadata_file in $test_images; do
  total=$((total + 1))
  image_dir=$(dirname "$metadata_file")
  image_name=$(basename "$image_dir")

  # Read version from metadata.yaml
  version=$(grep '^version:' "$metadata_file" | sed 's/version: *"\?\([^"]*\)"\?/\1/')

  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "Testing: $image_name (version: $version)"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

  # Generate tags using shared script
  generate_tags "$image_name" "$version"

  echo "  VERSION: $version"
  echo "  TAG: $TAG"
  echo "  RELEASE_TAG: $RELEASE_TAG"

  # Validate tags
  if validate_tags; then
    echo "  ✅ Tag validation passed"

    # Verify TAG has slashes converted to dashes
    expected_tag=$(echo "$version" | tr '/' '-')
    if [ "$TAG" != "$expected_tag" ]; then
      echo "  ::error::TAG conversion incorrect (expected: $expected_tag, got: $TAG)"
      failed=$((failed + 1))
      continue
    fi

    # Verify RELEASE_TAG format
    expected_release="${image_name}-${TAG}"
    if [ "$RELEASE_TAG" != "$expected_release" ]; then
      echo "  ::error::RELEASE_TAG incorrect (expected: $expected_release, got: $RELEASE_TAG)"
      failed=$((failed + 1))
      continue
    fi

    echo "  ✅ All validations passed"
    passed=$((passed + 1))
  else
    echo "  ❌ Tag validation failed"
    failed=$((failed + 1))
  fi
done

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Test Summary"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Total: $total"
echo "Passed: $passed"
echo "Failed: $failed"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ $failed -gt 0 ]; then
  echo "::error::$failed test fixture(s) failed validation"
  exit 1
fi

echo "✅ All $total test fixture images passed validation"
