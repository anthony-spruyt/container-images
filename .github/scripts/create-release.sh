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

# Source shared version handling functions
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/version-handling.sh"

# Generate release tag
generate_tags "$IMAGE_NAME" "$TAG"

# Check if release already exists
if gh release view "$RELEASE_TAG" &>/dev/null; then
  echo "Release $RELEASE_TAG already exists, skipping"
  exit 0
fi

# Generate release notes
cat <<EOF > /tmp/release-notes.md
## Container Image

**Image:** \`${REGISTRY}/${OWNER}/${IMAGE_NAME}:${TAG}\`
**Digest:** \`${DIGEST}\`

### Pull Commands
\`\`\`bash
docker pull ${REGISTRY}/${OWNER}/${IMAGE_NAME}:${TAG}
docker pull ${REGISTRY}/${OWNER}/${IMAGE_NAME}@${DIGEST}
\`\`\`

### Build Info
- **Upstream:** ${UPSTREAM:+[${UPSTREAM}](https://github.com/${UPSTREAM})}${UPSTREAM:-N/A (local Dockerfile)}
- **Build Commit:** ${SHA}
- **Workflow Run:** [#${RUN_NUMBER}](${SERVER_URL}/${REPO}/actions/runs/${RUN_ID})

### Security
- Trivy vulnerability scan: Passed (CRITICAL/HIGH)
- SBOM: Included in image
- Provenance: Attested
EOF

# Create release
gh release create "$RELEASE_TAG" \
  --title "${IMAGE_NAME} ${TAG}" \
  --notes-file /tmp/release-notes.md

echo "✅ Created release: $RELEASE_TAG"
