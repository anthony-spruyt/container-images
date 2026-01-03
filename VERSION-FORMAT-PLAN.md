# Simplify Version Handling and Fix n8n Workflows

## Overview

Simplify version/tag handling in CI workflows and fix broken n8n release watcher workflows. Remove complex 'v' prefix manipulation logic that causes bugs and makes n8n workflows fail.

## Problem Statement

### Current Issues

1. **Workflow Complexity**: Strips 'v' prefix then adds it back (`TAG_WITHOUT_V="${TAG#v}"` then `RELEASE_TAG="${IMAGE_NAME}-v${TAG_WITHOUT_V}"`)
2. **n8n Flows Broken**: Strip 'v' prefix before sending to workflow, but workflow needs exact upstream tag for `git checkout`
3. **Recently Fixed Double 'v' Bug**: `sungather-vv0.5.3` was created because workflow added 'v' to version that already had 'v'
4. **Inconsistent Behavior**: Different handling for versions with/without 'v' prefix

### Why n8n Flows Are Broken

**Current broken flow:**

1. SunGather upstream has tag: `v0.5.3`
2. n8n workflow strips 'v': `0.5.3`
3. n8n sends to GitHub Actions: `version=0.5.3`
4. GitHub Actions workflow runs: `git checkout 0.5.3`
5. **FAILS**: Git can't find ref `0.5.3` (upstream tag is `v0.5.3`)

**This affects:**

- `sungather/n8n-release-watcher.json` - Will fail when triggered automatically
- `firemerge/n8n-release-watcher.json` - Works only because upstream has no 'v' prefix

## Proposed Solution

**Principle: Use version as-is from source, no string manipulation**

### 1. Workflow Simplification

**File:** `.github/workflows/image-pipeline.yaml`

**Current code (lines 144-151):**

```yaml
# Validate release tag format (if release will be created)
# Strip leading 'v' if present to avoid double 'v' in release tag
TAG_WITHOUT_V="${TAG#v}"
RELEASE_TAG="${IMAGE_NAME}-v${TAG_WITHOUT_V}"
if ! echo "$RELEASE_TAG" | grep -qE '^[a-zA-Z0-9_-]+-v[a-zA-Z0-9._-]+$'; then
echo "::error::Release tag '$RELEASE_TAG' has invalid format"
ERRORS=$((ERRORS + 1))
fi
```

**New code:**

```yaml
# Validate release tag format (if release will be created)
RELEASE_TAG="${IMAGE_NAME}-${TAG}"
if ! echo "$RELEASE_TAG" | grep -qE '^[a-zA-Z0-9_-]+-[a-zA-Z0-9._-]+$'; then
echo "::error::Release tag '$RELEASE_TAG' has invalid format"
ERRORS=$((ERRORS + 1))
fi
```

**Current code (lines 338-344):**

```yaml
run: |
  # Strip leading 'v' if present to avoid double 'v' in release tag
  TAG_WITHOUT_V="${TAG#v}"
  RELEASE_TAG="${IMAGE_NAME}-v${TAG_WITHOUT_V}"
  if gh release view "$RELEASE_TAG" &>/dev/null; then
    echo "Release $RELEASE_TAG already exists, skipping"
    exit 0
  fi
```

**New code:**

```yaml
run: |
  RELEASE_TAG="${IMAGE_NAME}-${TAG}"
  if gh release view "$RELEASE_TAG" &>/dev/null; then
    echo "Release $RELEASE_TAG already exists, skipping"
    exit 0
  fi
```

**Also update line 366:**

```yaml
# Current:
--title "${IMAGE_NAME} v${TAG}" \

# New:
--title "${IMAGE_NAME} ${TAG}" \
```

### 2. Fix sungather n8n Workflow

**File:** `sungather/n8n-release-watcher.json`

**Current JavaScript (Check New Version node):**

```javascript
// Extract version (strip 'v' prefix if present)
let version = latestTag.name
if (version.startsWith("v")) {
  version = version.substring(1)
}

// Check if this is a new version
const lastVersion = staticData.lastVersion_sungather || null
const isNew = lastVersion !== version

return [
  {
    json: {
      isNew: isNew,
      version: version,
      lastVersion: lastVersion,
      tagName: latestTag.name,
      commitSha: latestTag.commit?.sha || null,
    },
  },
]
```

**New JavaScript:**

```javascript
// Keep version as-is from upstream tag (needed for git checkout)
const version = latestTag.name

// Check if this is a new version
const lastVersion = staticData.lastVersion_sungather || null
const isNew = lastVersion !== version

return [
  {
    json: {
      isNew: isNew,
      version: version,
      lastVersion: lastVersion,
      commitSha: latestTag.commit?.sha || null,
    },
  },
]
```

**Note:** Also remove `tagName` from output since it's redundant with `version`

### 3. Fix firemerge n8n Workflow

**File:** `firemerge/n8n-release-watcher.json`

Same changes as sungather - remove the v-stripping logic and keep version as-is.

### 4. Add Validation Tests

**New file:** `.github/workflows/test-version-handling.yaml`

```yaml
---
name: Test Version Handling

on:
  workflow_dispatch:
    inputs:
      test_version:
        description: "Version to test (e.g., v0.5.3, 0.5.3, viscious-llama)"
        required: true
        type: string

jobs:
  test-version-format:
    name: Test Version Format Handling
    runs-on: ubuntu-latest
    steps:
      - name: Test release tag generation
        env:
          IMAGE_NAME: "test-image"
          VERSION: ${{ inputs.test_version }}
        run: |
          # Simulate workflow logic
          TAG=$(echo "$VERSION" | tr '/' '-')
          RELEASE_TAG="${IMAGE_NAME}-${TAG}"

          echo "Input version: $VERSION"
          echo "Docker tag: $TAG"
          echo "Release tag: $RELEASE_TAG"

          # Validate release tag format
          if ! echo "$RELEASE_TAG" | grep -qE '^[a-zA-Z0-9_-]+-[a-zA-Z0-9._-]+$'; then
            echo "::error::Invalid release tag format: $RELEASE_TAG"
            exit 1
          fi

          echo "✅ Version format valid"

      - name: Test various formats
        run: |
          test_version() {
            local VERSION="$1"
            local EXPECTED_DOCKER="$2"
            local EXPECTED_RELEASE="$3"

            TAG=$(echo "$VERSION" | tr '/' '-')
            RELEASE_TAG="test-image-${TAG}"

            if [ "$TAG" != "$EXPECTED_DOCKER" ]; then
              echo "::error::Docker tag mismatch for $VERSION: got $TAG, expected $EXPECTED_DOCKER"
              return 1
            fi

            if [ "$RELEASE_TAG" != "$EXPECTED_RELEASE" ]; then
              echo "::error::Release tag mismatch for $VERSION: got $RELEASE_TAG, expected $EXPECTED_RELEASE"
              return 1
            fi

            echo "✅ $VERSION → Docker: $TAG, Release: $RELEASE_TAG"
          }

          test_version "v0.5.3" "v0.5.3" "test-image-v0.5.3"
          test_version "0.5.3" "0.5.3" "test-image-0.5.3"
          test_version "viscious-llama" "viscious-llama" "test-image-viscious-llama"
          test_version "security/fix-cve-2025-123" "security-fix-cve-2025-123" "test-image-security-fix-cve-2025-123"
          test_version "1.2.3-beta.1" "1.2.3-beta.1" "test-image-1.2.3-beta.1"

          echo "✅ All version format tests passed"
```

### 5. Update Documentation

**File:** `sungather/README.md` and `firemerge/README.md`

Update n8n workflow documentation to clarify that version is preserved as-is:

```markdown
### What it does

1. Checks GitHub daily (midnight UTC) for new tags on upstream repository
2. Compares with the last processed version (stored in workflow static data)
3. If a new version is found:
   - Triggers the container build workflow with the exact upstream tag
   - Sends an email notification
   - Updates the stored version

**Note:** The workflow preserves the exact upstream tag format (including 'v' prefix if present) to ensure correct git checkout.
```

## Implementation Steps

### Step 1: Create Issue

```bash
gh issue create --title "refactor(ci): simplify version handling and fix n8n workflows" \
  --body "See plan file for details" \
  --label enhancement
```

### Step 2: Create Feature Branch

```bash
git checkout main
git pull
git checkout -b refactor/simplify-version-handling
```

### Step 3: Update Workflow File

Edit `.github/workflows/image-pipeline.yaml`:

- Remove `TAG_WITHOUT_V` variable in both locations
- Change `RELEASE_TAG="${IMAGE_NAME}-v${TAG_WITHOUT_V}"` to `RELEASE_TAG="${IMAGE_NAME}-${TAG}"`
- Update regex validation to remove mandatory 'v' prefix
- Update release title format

### Step 4: Update sungather n8n Workflow

Edit `sungather/n8n-release-watcher.json`:

- Remove v-stripping logic from "Check New Version" node
- Keep version as-is from upstream tag
- Remove redundant `tagName` field from output

### Step 5: Update firemerge n8n Workflow

Edit `firemerge/n8n-release-watcher.json`:

- Same changes as sungather

### Step 6: Add Validation Tests

Create `.github/workflows/test-version-handling.yaml` with test cases

### Step 7: Update Documentation

Update README files for both sungather and firemerge

### Step 8: Run Pre-commit Hooks

```bash
pre-commit run --all-files
```

### Step 9: Commit Changes

```bash
git add .
git commit -m "refactor(ci): simplify version handling and fix n8n workflows

- Remove complex 'v' prefix stripping/adding logic from workflow
- Use version as-is from metadata.yaml or workflow input
- Fix n8n workflows to preserve exact upstream tag format
- Add validation tests for different version formats
- Update documentation

BREAKING CHANGE: Release tag format changes for images without 'v' prefix:
- firemerge-v0.5.2 → firemerge-0.5.2
- chrony-v0.1.1 → chrony-0.1.1
- sungather-v0.5.3 → sungather-v0.5.3 (unchanged)

This fixes n8n workflows that would fail on automatic trigger due to
incorrect git ref (stripped 'v' prefix but upstream tags have 'v').

Closes #XX

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

### Step 10: Push and Create PR

```bash
git push -u origin refactor/simplify-version-handling
gh pr create --title "refactor(ci): simplify version handling and fix n8n workflows" \
  --body "Fixes #XX

## Changes

- Simplified workflow RELEASE_TAG logic (no more v-stripping/adding)
- Fixed n8n workflows to preserve exact upstream tag format
- Added validation tests for different version formats
- Updated documentation

## Testing

Run validation tests:
\`\`\`bash
gh workflow run test-version-handling.yaml --field test_version=v0.5.3
gh workflow run test-version-handling.yaml --field test_version=0.5.3
gh workflow run test-version-handling.yaml --field test_version=viscious-llama
\`\`\`

## Breaking Changes

Release tag format changes for images without 'v' prefix in upstream/metadata:
- firemerge: \`firemerge-v0.5.2\` → \`firemerge-0.5.2\`
- chrony: \`chrony-v0.1.1\` → \`chrony-0.1.1\`
- sungather: \`sungather-v0.5.3\` → unchanged (upstream has 'v')

This is necessary to fix n8n workflows that would fail due to git checkout with incorrect ref."
```

### Step 11: Wait for CI and Run Tests

```bash
# Wait for CI checks
sleep 60 && gh pr checks

# Manually trigger validation tests via workflow_dispatch
gh workflow run test-version-handling.yaml --ref refactor/simplify-version-handling --field test_version=v0.5.3
gh workflow run test-version-handling.yaml --ref refactor/simplify-version-handling --field test_version=0.5.3
gh workflow run test-version-handling.yaml --ref refactor/simplify-version-handling --field test_version=viscious-llama
```

### Step 12: Verify Test Results

```bash
gh run list --workflow=test-version-handling.yaml --limit 3
gh run view <run-id> --log
```

### Step 13: Merge PR

```bash
gh pr merge --squash --delete-branch
```

### Step 14: Verify Fix Works End-to-End

Test with sungather (upstream has 'v' prefix):

```bash
gh workflow run build-and-push.yaml \
  --ref main \
  --field image=sungather \
  --field version=v0.5.3 \
  --field dry_run=false
```

Expected:

- Docker tag: `v0.5.3`
- Release tag: `sungather-v0.5.3`
- Git checkout: `v0.5.3` (works!)

Test with firemerge (upstream no 'v' prefix):

```bash
gh workflow run build-and-push.yaml \
  --ref main \
  --field image=firemerge \
  --field version=0.5.2 \
  --field dry_run=false
```

Expected:

- Docker tag: `0.5.2`
- Release tag: `firemerge-0.5.2`
- Git checkout: `0.5.2` (works!)

## Expected Outcomes

### Before (Broken)

- n8n sends `version=0.5.3` for upstream tag `v0.5.3`
- Workflow runs `git checkout 0.5.3`
- **FAILS** - tag doesn't exist

### After (Fixed)

- n8n sends `version=v0.5.3` for upstream tag `v0.5.3`
- Workflow runs `git checkout v0.5.3`
- **SUCCESS** - tag exists

### Version Format Examples

| Upstream Tag       | metadata.yaml      | Docker Tag         | Release Tag                  | Status   |
| ------------------ | ------------------ | ------------------ | ---------------------------- | -------- |
| `v0.5.3`           | `v0.5.3`           | `v0.5.3`           | `sungather-v0.5.3`           | ✅ Works |
| `0.5.3`            | `0.5.3`            | `0.5.3`            | `firemerge-0.5.3`            | ✅ Works |
| `security/fix-cve` | `security/fix-cve` | `security-fix-cve` | `firemerge-security-fix-cve` | ✅ Works |
| `viscious-llama`   | `viscious-llama`   | `viscious-llama`   | `test-viscious-llama`        | ✅ Works |

## Files to Modify

1. `.github/workflows/image-pipeline.yaml` - Simplify RELEASE_TAG logic
2. `sungather/n8n-release-watcher.json` - Remove v-stripping
3. `firemerge/n8n-release-watcher.json` - Remove v-stripping
4. `.github/workflows/test-version-handling.yaml` - New validation tests
5. `sungather/README.md` - Update documentation
6. `firemerge/README.md` - Update documentation

## Testing Strategy

### Unit Tests

- Test version format validation with various inputs
- Verify release tag generation for different formats

### Integration Tests

- Test actual builds with different version formats
- Verify git checkout works with exact upstream tags
- Verify release creation with correct tags

### Regression Tests

- Ensure existing images still build correctly
- Verify n8n workflows trigger correctly
- Check release tag format consistency

## Risks and Mitigations

### Risk: Breaking Existing Release Tags

- **Impact**: Release tag format changes for some images
- **Mitigation**: Document breaking change, update metadata.yaml if needed

### Risk: n8n Workflows Need Re-import

- **Impact**: Users with existing n8n workflows need to update
- **Mitigation**: Provide clear migration instructions in README

### Risk: Existing Automation May Break

- **Impact**: Tools expecting `v` prefix in all release tags
- **Mitigation**: Document change in CHANGELOG, communicate in PR

## Success Criteria

- [ ] Workflow simplified (no TAG_WITHOUT_V variable)
- [ ] n8n flows preserve exact upstream tag format
- [ ] Validation tests pass for all version formats
- [ ] sungather build succeeds with upstream tag `v0.5.3`
- [ ] firemerge build succeeds with upstream tag `0.5.2`
- [ ] Release tags created correctly for all formats
- [ ] Documentation updated
- [ ] No lint/pre-commit errors

## Reference

- Original double 'v' bug: PR #45
- n8n workflow pattern: `sungather/n8n-release-watcher.json`
- Upstream with 'v': https://github.com/bohdan-s/SunGather/tags
- Upstream without 'v': https://github.com/lvu/firemerge/tags
