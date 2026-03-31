# Registry Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix burned versions by verifying images exist in the container registry before
skipping builds, and create missing releases when the image exists but the release does not.

**Architecture:** Add `docker manifest inspect` to the `check-release` job. Add a new
`release-needed` output. Extract release creation into a separate job that runs when the
image exists but the release is missing. Update `create-release.sh` to handle updating
existing releases on re-push.

**Tech Stack:** GitHub Actions, bash, `gh` CLI, `docker manifest inspect`

---

## File Map

- Modify: `.github/workflows/_image-pipeline.yaml` (check-release outputs, GHCR login,
  registry verification, release-only job, push guard)
- Modify: `.github/scripts/create-release.sh` (update existing releases)

---

### Task 1: Add registry verification to `check-release` job

**Files:**

- Modify: `.github/workflows/_image-pipeline.yaml:57-173`

- [ ] **Step 1: Add `packages: read` permission and new outputs**

Change the `check-release` permissions and outputs. Replace:

```yaml
    permissions:
      contents: read # Read releases
    outputs:
      should-build: ${{ steps.check.outputs.should-build }}
      tag: ${{ steps.metadata.outputs.tag }}
      version: ${{ steps.metadata.outputs.version }}
      upstream: ${{ steps.metadata.outputs.upstream }}
```

with:

```yaml
    permissions:
      contents: read # Read releases
      packages: read # Verify image exists in registry
    outputs:
      should-build: ${{ steps.check.outputs.should-build }}
      release-needed: ${{ steps.check.outputs.release-needed }}
      image-exists: ${{ steps.check.outputs.image-exists }}
      tag: ${{ steps.metadata.outputs.tag }}
      version: ${{ steps.metadata.outputs.version }}
      upstream: ${{ steps.metadata.outputs.upstream }}
```

- [ ] **Step 2: Add GHCR login step after the Checkout step**

Insert a new step after the existing "Checkout" step (line 69) and before "Read metadata":

```yaml
      - name: Log in to GHCR (read-only)
        uses: docker/login-action@a0d57b8e43b6ef1cca20559d68cec2227e63fccd
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
```

Uses the same pinned SHA as the build job's login step (line 247).

- [ ] **Step 3: Replace the "Check if release exists" step with registry-aware logic**

Replace the entire `check` step run script (lines 140-173). Also add `REGISTRY` and `OWNER`
to the step's env block. The full step becomes:

```yaml
      - name: Check if release exists
        id: check
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          IMAGE_NAME: ${{ inputs.image }}
          TAG: ${{ steps.metadata.outputs.tag }}
          CREATE_RELEASE: ${{ inputs.create-release }}
          REGISTRY: ${{ env.REGISTRY }}
          OWNER: ${{ env.OWNER }}
        run: |
          # Always build for dry runs or when not creating releases
          if [ "$CREATE_RELEASE" != "true" ]; then
            echo "::notice::Dry run mode, will build"
            echo "should-build=true" >> "$GITHUB_OUTPUT"
            exit 0
          fi

          RELEASE_TAG="${IMAGE_NAME}-${TAG}"
          IMAGE_REF="${REGISTRY}/${OWNER}/${IMAGE_NAME}:${TAG}"

          # Helper: check if image exists in registry
          verify_image_in_registry() {
            if docker manifest inspect "$IMAGE_REF" > /dev/null 2>&1; then
              echo "::notice::Image $IMAGE_REF exists in registry"
              echo "image-exists=true" >> "$GITHUB_OUTPUT"
              return 0
            else
              echo "::warning::Image $IMAGE_REF NOT found in registry"
              echo "image-exists=false" >> "$GITHUB_OUTPUT"
              return 1
            fi
          }

          # Helper: check if a GitHub release exists for this tag
          release_exists() {
            if gh release view "$RELEASE_TAG" &>/dev/null; then
              return 0
            fi
            # Check for releases with -rN suffix (immutable tag retries)
            if gh release list --limit 100 2>/dev/null \
              | grep -qE "[[:space:]]${RELEASE_TAG}(-r[0-9]+)?[[:space:]]"; then
              return 0
            fi
            return 1
          }

          # Check if any tag or release exists
          HAS_RELEASE=false
          HAS_TAG=false

          if release_exists; then
            HAS_RELEASE=true
            HAS_TAG=true
          elif git ls-remote --tags origin "refs/tags/${RELEASE_TAG}*" 2>/dev/null | grep -q .; then
            HAS_TAG=true
          fi

          # Nothing exists — fresh build
          if [ "$HAS_TAG" = "false" ]; then
            echo "::notice::Release $RELEASE_TAG does not exist, will build"
            echo "should-build=true" >> "$GITHUB_OUTPUT"
            exit 0
          fi

          # Tag/release exists — verify image is in registry
          if verify_image_in_registry; then
            # Image exists in registry
            if [ "$HAS_RELEASE" = "true" ]; then
              echo "::notice::Release and image both exist, skipping"
              echo "should-build=false" >> "$GITHUB_OUTPUT"
            else
              echo "::warning::Image exists but release is missing, will create release"
              echo "should-build=false" >> "$GITHUB_OUTPUT"
              echo "release-needed=true" >> "$GITHUB_OUTPUT"
            fi
          else
            # Image missing — rebuild
            echo "::warning::Tag exists but image missing (burned version), will rebuild"
            echo "should-build=true" >> "$GITHUB_OUTPUT"
          fi
```

- [ ] **Step 4: Run linter to verify workflow syntax**

Run: `pre-commit run --all-files`

Expected: All checks pass (yamllint, actionlint).

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/_image-pipeline.yaml
git commit -m "fix(image-pipeline): verify image exists in registry before skipping build"
```

---

### Task 2: Add release-only job and push guard

**Files:**

- Modify: `.github/workflows/_image-pipeline.yaml:175-394`

- [ ] **Step 1: Add `inputs.push` guard to the release creation step in the build job**

Change line 379 from:

```yaml
        if: inputs.create-release && needs.check-release.outputs.tag != 'latest'
```

to:

```yaml
        if: inputs.push && inputs.create-release && needs.check-release.outputs.tag != 'latest'
```

- [ ] **Step 2: Add a `create-release` job for the release-only recovery path**

Add a new job after the `build` job. This handles the case where the image exists in the
registry but the GitHub release is missing (e.g., the `claude-agent-1.0.1` scenario).

```yaml
  create-release:
    name: Create Missing Release
    needs: check-release
    if: >-
      needs.check-release.outputs.should-build == 'false' &&
      needs.check-release.outputs.release-needed == 'true' &&
      needs.check-release.outputs.tag != 'latest'
    runs-on: ubuntu-latest
    permissions:
      contents: write # Release creation
      packages: read # Read image digest
    steps:
      - name: Checkout
        uses: actions/checkout@0c366fd6a839edf440554fa01a7085ccba70ac98

      - name: Log in to GHCR (read-only)
        uses: docker/login-action@a0d57b8e43b6ef1cca20559d68cec2227e63fccd
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Get image digest
        id: digest
        env:
          REGISTRY: ${{ env.REGISTRY }}
          OWNER: ${{ env.OWNER }}
          IMAGE_NAME: ${{ inputs.image }}
          TAG: ${{ needs.check-release.outputs.tag }}
        run: |
          IMAGE_REF="${REGISTRY}/${OWNER}/${IMAGE_NAME}:${TAG}"
          DIGEST=$(docker manifest inspect "$IMAGE_REF" -v 2>/dev/null \
            | jq -r 'if type == "array" then .[0].Descriptor.digest else .Descriptor.digest end')
          if [ -z "$DIGEST" ] || [ "$DIGEST" = "null" ]; then
            echo "::error::Could not get digest for $IMAGE_REF"
            exit 1
          fi
          echo "digest=$DIGEST" >> "$GITHUB_OUTPUT"
          echo "::notice::Image digest: $DIGEST"

      - name: Create GitHub Release
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          IMAGE_NAME: ${{ inputs.image }}
          TAG: ${{ needs.check-release.outputs.tag }}
          DIGEST: ${{ steps.digest.outputs.digest }}
          UPSTREAM: ${{ needs.check-release.outputs.upstream }}
          REGISTRY: ${{ env.REGISTRY }}
          OWNER: ${{ env.OWNER }}
          SHA: ${{ github.sha }}
          RUN_NUMBER: ${{ github.run_number }}
          RUN_ID: ${{ github.run_id }}
          SERVER_URL: ${{ github.server_url }}
          REPO: ${{ github.repository }}
        run: .github/scripts/create-release.sh
```

- [ ] **Step 3: Run linter to verify workflow syntax**

Run: `pre-commit run --all-files`

Expected: All checks pass.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/_image-pipeline.yaml
git commit -m "fix(image-pipeline): add release-only job for missing releases"
```

---

### Task 3: Update `create-release.sh` to handle existing releases

**Files:**

- Modify: `.github/scripts/create-release.sh`

- [ ] **Step 1: Restructure the script to generate notes before the release-exists check**

The current script generates release notes at lines 110-152, then creates the release at
line 155. We need to move note generation before the release-exists check (line 30) so
that `gh release edit` can use the notes file.

Rewrite the main body of `create-release.sh` (everything after the function definitions,
starting at line 110). The function definitions (`create_release_with_retry`,
`get_previous_release`, `generate_local_changelog` at lines 37-107) stay unchanged.

Replace lines 28-155 (from `generate_tags` to end of file) with:

```bash
# Generate release tag
generate_tags "$IMAGE_NAME" "$TAG"

# --- Generate release notes ---

# Set upstream display value
if [ -n "$UPSTREAM" ]; then
  UPSTREAM_DISPLAY="[${UPSTREAM}](https://github.com/${UPSTREAM})"
else
  UPSTREAM_DISPLAY="N/A (local Dockerfile)"
fi

# Generate changelog section
PREV_RELEASE=$(get_previous_release "$IMAGE_NAME" "$TAG")

if [ -n "$UPSTREAM" ]; then
  CHANGELOG="See [${UPSTREAM} release ${TAG}](https://github.com/${UPSTREAM}/releases/tag/${TAG})"
else
  CHANGELOG=$(generate_local_changelog "$IMAGE_NAME" "$PREV_RELEASE")
fi

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

# --- Create or update release ---

# If release already exists, update it with new digest/notes
if gh release view "$RELEASE_TAG" &>/dev/null; then
  echo "::notice::Release $RELEASE_TAG already exists, updating with new digest"
  gh release edit "$RELEASE_TAG" \
    --title "${IMAGE_NAME} ${TAG}" \
    --notes-file "/tmp/release-notes.md"
  echo "Updated release: $RELEASE_TAG"
  exit 0
fi

# Create release with retry logic for immutable tags
create_release_with_retry "$RELEASE_TAG" "/tmp/release-notes.md" "${IMAGE_NAME} ${TAG}"
```

- [ ] **Step 2: Run shellcheck and shfmt**

Run: `pre-commit run --all-files`

Expected: All checks pass (shellcheck, shfmt, etc.).

- [ ] **Step 3: Commit**

```bash
git add .github/scripts/create-release.sh
git commit -m "fix(image-pipeline): update existing release on re-push instead of skipping"
```

---

### Task 4: Final validation and squash

- [ ] **Step 1: Run full linter suite**

Run: `pre-commit run --all-files`

Expected: All checks pass.

- [ ] **Step 2: Review the complete diff**

Run: `git diff main --stat && git diff main`

Verify:

- Only two files changed: `_image-pipeline.yaml` and `create-release.sh`
- No unintended changes
- The `docker/login-action` SHA matches the one in the build job
  (`a0d57b8e43b6ef1cca20559d68cec2227e63fccd`)
- The `verify_image_in_registry` function uses the base Docker tag (`$TAG`),
  not the release tag with `-rN` suffix
- The `create-release` job condition correctly gates on
  `release-needed == 'true'` and `should-build == 'false'`

- [ ] **Step 3: Squash into a single commit for the PR**

Run: `git log --oneline main..HEAD` to see the commits, then:

```bash
git reset --soft main
git add .github/workflows/_image-pipeline.yaml .github/scripts/create-release.sh
git commit -m "fix(image-pipeline): verify registry image exists before skipping release

When a tag/release exists, check that the image is actually in GHCR
using docker manifest inspect before deciding to skip a build.

Decision matrix:
- Release + image exist: skip (as before)
- Release exists, image missing: rebuild and update release
- Tag exists, no release, image exists: create missing release
- Tag exists, image missing: rebuild

Also:
- Add GHCR login (read-only) in check-release for manifest inspection
- Add create-release job for the release-only recovery path
- Update create-release.sh to edit existing releases on re-push
- Add inputs.push guard to release creation step

Closes #427"
```
