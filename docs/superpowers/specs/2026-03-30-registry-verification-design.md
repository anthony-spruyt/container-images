# Registry Verification in Image Pipeline

## Problem

When an image build succeeds but the push to GHCR fails (e.g., HTTP 502), the GitHub release/tag may still be created. On retry, the pipeline sees the existing tag and skips the build, leaving a "burned" version with no published image.

Reference: [#427](https://github.com/anthony-spruyt/container-images/issues/427)

### Root Cause Analysis

Evidence from [run 23744834973][run] shows the actual failure mode:

1. **Push image: SUCCESS** — image exists in GHCR (`ghcr.io/anthony-spruyt/claude-agent:1.0.1`)
1. **Create GitHub Release: FAILURE** — no release was created
1. **Git tag left behind** — `claude-agent-1.0.1` tag exists

On next run, `check-release` sees the git tag and skips the build entirely. The image is in the registry but there is no GitHub release.

This means the fix needs to handle two scenarios:

- **Image missing + tag exists:** rebuild and push, then create/update release
- **Image exists + tag exists + no release:** skip the build, but still create the release

## Solution

Add a container registry verification step in the `check-release` job. When a tag or release already exists, verify the image is actually present in the registry using `docker manifest inspect`. If the image is missing, proceed with the build instead of skipping.

Update `create-release.sh` to handle updating an existing release with the correct digest instead of silently exiting.

## Changes

### 1. `_image-pipeline.yaml` — `check-release` job

**Permissions:** Add `packages: read` to enable registry inspection.

**New step: GHCR login (read-only).** Use `docker/login-action` (same as the build job) for consistency and credential masking. Required for `docker manifest inspect` against private GHCR packages. Uses existing `GITHUB_TOKEN`.

**Modified step: "Check if release exists".** After each of the three skip conditions (release exists, release with `-rN` suffix, git tag exists), call:

```bash
docker manifest inspect ghcr.io/$OWNER/$IMAGE_NAME:$TAG
```

Note: always inspect the base Docker tag (e.g., `1.0.0`), not the release tag with `-rN` suffix.

**Decision matrix:**

| Release exists? | Image in registry? | Action                                                                   |
| --------------- | ------------------ | ------------------------------------------------------------------------ |
| Yes             | Yes                | Skip build (`should-build=false`)                                        |
| Yes             | No                 | Rebuild (`should-build=true`)                                            |
| No (tag only)   | Yes                | Skip build, create release (`should-build=false`, `release-needed=true`) |
| No (tag only)   | No                 | Rebuild (`should-build=true`)                                            |

**New output: `release-needed`.** When the image exists but the release does not, set `release-needed=true`. The build job uses this to run the release creation step even when the build was skipped.

Log the `manifest inspect` result to the step summary for debugging visibility.

**Additional fix: Add `inputs.push` guard to release creation step.** The existing condition on the "Create GitHub Release" step checks `inputs.create-release` but not `inputs.push`. Add `inputs.push` to prevent creating releases when no push occurred:

```yaml
if: inputs.push && inputs.create-release && needs.check-release.outputs.tag != 'latest'
```

### 2. `create-release.sh` — Handle existing releases

Currently, when a release already exists, the script exits with 0 (skip). Change this to:

1. **Release exists:** Update the existing release with the new digest and notes using `gh release edit`, so the release reflects the actual pushed image.
1. **Tag exists but no release:** Create a new release for the existing tag using `gh release create` (the existing `create_release_with_retry` function already handles this).

### 3. No new files

All changes are in existing files:

- `.github/workflows/_image-pipeline.yaml`
- `.github/scripts/create-release.sh`

## Flows

### Normal (image + release both exist)

```text
check-release: release exists, manifest inspect OK
  -> should-build=false, release-needed=false
  -> build job skipped
```

### Recovery A: image missing (burned version)

```text
check-release: tag exists, manifest inspect FAIL
  -> should-build=true
  -> build: rebuild, push, create/update release
```

### Recovery B: image exists, release missing (the claude-agent-1.0.1 case)

```text
check-release: tag exists (no release), manifest inspect OK
  -> should-build=false, release-needed=true
  -> build job skipped, but release-only job creates the release
```

## Permissions

- `check-release` job: `packages: read` added (was only `contents: read`)
- GHCR login uses existing `GITHUB_TOKEN` via `docker/login-action` — no new secrets

## Testing

- Manual `workflow_dispatch` with a known burned version to verify recovery
- Normal push to verify the happy path still skips correctly
- The registry check is a single `docker manifest inspect` call — failure modes are: image missing (proceed with build) or network error (fail-safe: proceed with build)

## Known Limitations

- Only the version tag is checked via `manifest inspect`. If the push partially succeeded (version tag pushed but `latest` tag failed), the build will be skipped and `latest` may be stale. The version tag is the critical one; `latest` is updated on the next build.

[run]: https://github.com/anthony-spruyt/container-images/actions/runs/23744834973/job/69170876586
