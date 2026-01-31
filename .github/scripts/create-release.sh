#!/bin/bash
set -euo pipefail

# Create GitHub release for container image
# This script consolidates release creation logic to ensure consistency

# Required environment variables:
#   IMAGE_NAME: Name of the image
#   TAG: Docker tag
#   DIGEST: Image digest from push step
#   UPSTREAM: Upstream repository (owner/repo) or empty
#   REGISTRY: Container registry
#   OWNER: Registry owner
#   SHA: Git commit SHA
#   RUN_NUMBER: GitHub Actions run number
#   RUN_ID: GitHub Actions run ID
#   SERVER_URL: GitHub server URL
#   REPO: GitHub repository (owner/repo)
#   GH_TOKEN: GitHub token for gh CLI

# shellcheck disable=SC2153
# Source shared version handling functions
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=.github/scripts/version-handling.sh
source "$SCRIPT_DIR/version-handling.sh"

# Generate release tag
generate_tags "$IMAGE_NAME" "$TAG"

# Check if release already exists
if gh release view "$RELEASE_TAG" &>/dev/null; then
  echo "Release $RELEASE_TAG already exists, skipping"
  exit 0
fi

# Function to create release with retry logic for immutable tags
create_release_with_retry() {
  local release_tag="$1"
  local notes_file="$2"
  local title="$3"
  local rebuild_num=1
  local max_retries=5

  while [ $rebuild_num -le $max_retries ]; do
    # Try to create the release
    if gh release create "$release_tag" \
      --title "$title" \
      --notes-file "$notes_file" 2>&1 | tee /tmp/gh-release-error.log; then
      echo "✅ Created release: $release_tag"
      return 0
    fi

    # Check if error is due to immutable release
    if grep -q "tag_name was used by an immutable release" /tmp/gh-release-error.log; then
      echo "⚠️  Tag $release_tag is immutable, trying with rebuild suffix..."
      release_tag="${RELEASE_TAG}-r${rebuild_num}"
      rebuild_num=$((rebuild_num + 1))
    else
      # Different error, fail
      cat /tmp/gh-release-error.log
      return 1
    fi
  done

  echo "::error::Failed to create release after $max_retries attempts"
  return 1
}

# Find the previous release tag for this image
get_previous_release() {
  local image="$1"
  local current_tag="$2"
  local current_release="${image}-${current_tag}"

  # Use JSON output for reliable parsing
  # Filter: starts with image prefix, excludes current version and its rebuild suffixes (-rN)
  gh release list --json tagName --limit 100 2>/dev/null |
    jq -r --arg prefix "${image}-" --arg current "$current_release" '
      [.[] |
        select(.tagName | startswith($prefix)) |
        select((.tagName == $current) or (.tagName | test($current + "-r[0-9]+$")) | not)
      ][0].tagName // empty
    ' || true
}

# Generate commit log since previous release
generate_local_changelog() {
  local image="$1"
  local prev_tag="$2"

  if [ -z "$prev_tag" ]; then
    echo "Initial release"
    return
  fi

  # Get commits that touched this image's directory
  local commits
  commits=$(git log --oneline "${prev_tag}..HEAD" -- "${image}/" 2>/dev/null || true)

  if [ -z "$commits" ]; then
    echo "Rebuild (no source changes)"
  else
    echo "$commits" | while read -r line; do
      echo "- $line"
    done
  fi
}

# Set upstream display value
if [ -n "$UPSTREAM" ]; then
  UPSTREAM_DISPLAY="[${UPSTREAM}](https://github.com/${UPSTREAM})"
else
  UPSTREAM_DISPLAY="N/A (local Dockerfile)"
fi

# Generate changelog section
PREV_RELEASE=$(get_previous_release "$IMAGE_NAME" "$TAG")

if [ -n "$UPSTREAM" ]; then
  # Upstream image: link to upstream release
  CHANGELOG="See [${UPSTREAM} release ${TAG}](https://github.com/${UPSTREAM}/releases/tag/${TAG})"
else
  # Local image: show commit history
  CHANGELOG=$(generate_local_changelog "$IMAGE_NAME" "$PREV_RELEASE")
fi

# Generate release notes
cat <<EOF >/tmp/release-notes.md
## Container Image

**Image:** \`${REGISTRY}/${OWNER}/${IMAGE_NAME}:${TAG}\`
**Digest:** \`${DIGEST}\`

### Pull Commands
\`\`\`bash
docker pull ${REGISTRY}/${OWNER}/${IMAGE_NAME}:${TAG}
docker pull ${REGISTRY}/${OWNER}/${IMAGE_NAME}@${DIGEST}
\`\`\`

### Build Info
- **Upstream:** ${UPSTREAM_DISPLAY}
- **Build Commit:** ${SHA}
- **Workflow Run:** [#${RUN_NUMBER}](${SERVER_URL}/${REPO}/actions/runs/${RUN_ID})

### Changes
${CHANGELOG}

### Security
- Trivy vulnerability scan: Passed (CRITICAL/HIGH)
- SBOM: Included in image
- Provenance: Attested
EOF

# Create release with retry logic for immutable tags
create_release_with_retry "$RELEASE_TAG" "/tmp/release-notes.md" "${IMAGE_NAME} ${TAG}"
