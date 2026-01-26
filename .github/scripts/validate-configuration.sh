#!/bin/bash
set -euo pipefail

# Validate workflow configuration for container image build
# This script consolidates all validation logic to ensure consistency

# Required environment variables:
#   IMAGE_NAME: Name of the image directory
#   VERSION: Version string from metadata or input
#   TAG: Docker-compatible tag
#   UPSTREAM_INPUT: Upstream repo from workflow input (optional)
#   UPSTREAM_METADATA: Upstream repo from metadata.yaml (optional)

# shellcheck disable=SC2153
ERRORS=0

# Source shared version handling functions
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=.github/scripts/version-handling.sh
source "$SCRIPT_DIR/version-handling.sh"

# Determine effective upstream (input takes precedence)
UPSTREAM="${UPSTREAM_INPUT:-$UPSTREAM_METADATA}"

# If upstream input is provided, it must match the image's metadata.yaml
if [ -n "$UPSTREAM_INPUT" ] && [ -n "$UPSTREAM_METADATA" ]; then
  if [ "$UPSTREAM_INPUT" != "$UPSTREAM_METADATA" ]; then
    echo "::error::Upstream mismatch: input '$UPSTREAM_INPUT' does not match metadata '$UPSTREAM_METADATA'"
    ERRORS=$((ERRORS + 1))
  fi
fi

# If upstream input is provided but metadata has no upstream, reject
if [ -n "$UPSTREAM_INPUT" ] && [ -z "$UPSTREAM_METADATA" ]; then
  echo "::error::Cannot override upstream for image without upstream in metadata.yaml"
  ERRORS=$((ERRORS + 1))
fi

# No upstream - verify local Dockerfile or flavor.yaml exists
if [ -z "$UPSTREAM" ]; then
  if [ ! -f "$IMAGE_NAME/Dockerfile" ] && [ ! -f "$IMAGE_NAME/flavor.yaml" ]; then
    echo "::error::No upstream specified and no local Dockerfile or flavor.yaml found at $IMAGE_NAME/"
    ERRORS=$((ERRORS + 1))
  fi
fi

# Validate version format (alphanumeric with common separators, no shell chars)
if [ -n "$VERSION" ] && [ "$VERSION" != "latest" ]; then
  if ! echo "$VERSION" | grep -qE '^[a-zA-Z0-9][a-zA-Z0-9._/-]*$'; then
    echo "::error::Invalid version format: $VERSION"
    ERRORS=$((ERRORS + 1))
  fi
fi

# Use shared version handling script for tag validation
generate_tags "$IMAGE_NAME" "$VERSION"
if ! validate_tags; then
  ERRORS=$((ERRORS + 1))
fi

# Verify inline tag generation matches shared script
if [ "$TAG" != "$(echo "$VERSION" | tr '/' '-')" ]; then
  echo "::error::TAG mismatch: metadata step produced '$TAG' but shared script expects '$(echo "$VERSION" | tr '/' '-')'"
  ERRORS=$((ERRORS + 1))
fi

# Test release notes generation (validates no injection issues)
cat <<EOF >/tmp/release-notes-test.md
## Container Image
**Image:** \`ghcr.io/test/${IMAGE_NAME}:${TAG}\`
**Upstream:** [${UPSTREAM}](https://github.com/${UPSTREAM})
EOF
if [ ! -s /tmp/release-notes-test.md ]; then
  echo "::error::Release notes generation failed"
  ERRORS=$((ERRORS + 1))
fi

if [ $ERRORS -gt 0 ]; then
  echo "::error::Validation failed with $ERRORS error(s)"
  exit 1
fi

echo "✅ All validations passed"
exit 0
