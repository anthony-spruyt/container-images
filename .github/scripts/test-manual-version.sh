#!/bin/bash
set -euo pipefail

# Test script for manual version input validation
# Usage: ./test-manual-version.sh <version>

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ $# -lt 1 ]; then
  echo "Usage: $0 <version>"
  echo "Example: $0 v1.2.3"
  exit 1
fi

VERSION="$1"

# Source the version handling functions
# shellcheck source=.github/scripts/version-handling.sh
source "$SCRIPT_DIR/version-handling.sh"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Testing manual version input: $VERSION"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

generate_tags "manual-test" "$VERSION"

echo "  VERSION: $VERSION"
echo "  TAG: $TAG"
echo "  RELEASE_TAG: $RELEASE_TAG"

if ! validate_tags; then
  echo "::error::Manual test version validation failed"
  exit 1
fi

echo "✅ Manual test version validation passed"
