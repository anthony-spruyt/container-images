#!/bin/bash
set -euo pipefail

# Shared version handling logic for CI workflows
# This ensures consistency between validation tests and production workflows

# Usage:
#   source .github/scripts/version-handling.sh
#   generate_tags "my-image" "v0.5.3"
#   validate_tags

# Generate Docker tag and release tag from image name and version
# Args:
#   $1: IMAGE_NAME
#   $2: VERSION
# Sets:
#   TAG: Docker-compatible tag (/ replaced with -)
#   RELEASE_TAG: GitHub release tag (image-name-version)
generate_tags() {
    local image_name="$1"
    local version="$2"

    # Convert slashes to dashes for Docker tag
    TAG=$(echo "$version" | tr '/' '-')

    # Release tag is simply image-name-tag (no v-prefix manipulation)
    RELEASE_TAG="${image_name}-${TAG}"

    export TAG
    export RELEASE_TAG
}

# Validate that generated tags meet format requirements
# Requires: TAG and RELEASE_TAG to be set (by generate_tags)
# Returns: 0 if valid, 1 if invalid (with error messages)
validate_tags() {
    local errors=0

    # Validate Docker tag is OCI-compliant (lowercase alphanumeric, .-_)
    if ! echo "$TAG" | grep -qE '^[a-z0-9][a-z0-9._-]{0,127}$'; then
        echo "::error::Docker tag '$TAG' is not OCI-compliant"
        errors=$((errors + 1))
    fi

    # Validate release tag format
    if ! echo "$RELEASE_TAG" | grep -qE '^[a-zA-Z0-9_-]+-[a-zA-Z0-9._-]+$'; then
        echo "::error::Release tag '$RELEASE_TAG' has invalid format"
        errors=$((errors + 1))
    fi

    return $errors
}

# Test function for version format handling
# Args:
#   $1: VERSION to test
#   $2: Expected DOCKER tag
#   $3: Expected RELEASE tag
#   $4: IMAGE_NAME (default: "test-image")
# Returns: 0 if match, 1 if mismatch
test_version() {
    local version="$1"
    local expected_docker="$2"
    local expected_release="$3"
    local image_name="${4:-test-image}"

    generate_tags "$image_name" "$version"

    if [ "$TAG" != "$expected_docker" ]; then
        echo "::error::Docker tag mismatch for $version: got $TAG, expected $expected_docker"
        return 1
    fi

    if [ "$RELEASE_TAG" != "$expected_release" ]; then
        echo "::error::Release tag mismatch for $version: got $RELEASE_TAG, expected $expected_release"
        return 1
    fi

    echo "✅ $version → Docker: $TAG, Release: $RELEASE_TAG"
    return 0
}
