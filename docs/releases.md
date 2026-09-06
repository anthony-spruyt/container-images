# Releases

Image versions live in `.release-please-manifest.json`. [release-please][rp] owns them: it opens a release PR per image, and merging that PR creates the tag and a **draft** release. The image is built and pushed from the tag, and only then is the release published. A published release always has an image behind it.

## Images

| Image          | Git tag                 | Docker tag               |
| -------------- | ----------------------- | ------------------------ |
| llm-guard-cuda | `llm-guard-cuda/v1.0.7` | `1.0.7`, `1.0`, `latest` |

Images not listed here are still on the legacy pipeline (`_image-pipeline.yaml`) and derive their version from `metadata.yaml`.

## How a release happens

1. You merge a conventional commit that touches an image directory.
2. `Release Please` runs on `main` and opens (or updates) a release PR for that image, labelled `autorelease: pending`.
3. Mergify auto-merges the release PR once `summary / Check Results` passes.
4. Merging creates the git tag and a **draft** GitHub release.
5. The same workflow run builds the image from that tag, pushes it to GHCR, attests provenance, and publishes the release with the image ref and digest appended.

If step 5 fails, the release stays a draft and no image is published. Recover with [Rebuild Release](#rebuild-release).

## Version bumps

| Commit prefix                                          | Bump  |
| ------------------------------------------------------ | ----- |
| `fix:`, `chore:`, `docs:`, `ci:`, `refactor:`, `perf:` | patch |
| `feat:`                                                | minor |
| any type with `!` or a `BREAKING CHANGE:` footer       | major |

Only commits whose files sit inside the image's directory count towards that image's release.

To force a specific version, add a footer to the commit body:

```text
Release-As: 2.0.0
```

`chore` commits are visible in the changelog on purpose — release-please aborts a release with an empty changelog, so hiding them would break dependency-only releases.

## Pull request checks

On a PR, changed images build via `_build-image.yaml` with `push: false`. Nothing is pushed and no release is touched. `<image>/test.sh` runs against the locally loaded image if it exists.

## Rebuild Release

`Rebuild Release` (`.github/workflows/rebuild-release.yaml`) is the recovery path for a release that was tagged but whose build failed. Dispatch it with the image and the version (no leading `v`). It refuses to run unless all three hold:

- the git tag exists
- the release is still a draft
- no newer version of that image is already published

It never creates a release. If the tag does not exist, cut a new version instead.

## Configuration

| File                                     | Purpose                                           |
| ---------------------------------------- | ------------------------------------------------- |
| `release-please-config.json`             | Per-image release type, component, and tag format |
| `.release-please-manifest.json`          | Current version per image — the source of truth   |
| `.github/workflows/release-please.yaml`  | Cuts releases and dispatches builds               |
| `.github/workflows/_build-image.yaml`    | Reusable build/push/publish workflow              |
| `.github/workflows/rebuild-release.yaml` | Recovery for a tagged-but-unbuilt release         |

Notable settings:

| Setting                  | Why                                                        |
| ------------------------ | ---------------------------------------------------------- |
| `separate-pull-requests` | One release PR per image                                   |
| `always-update`          | Keeps sibling release PRs from conflicting on the manifest |
| `draft`                  | The release is published only after the image is pushed    |
| `force-tag-creation`     | Creates the tag alongside the draft release                |
| `tag-separator: "/"`     | Tags read `llm-guard-cuda/v1.0.7`                          |

## Adding an image

1. Add the directory to `packages` in `release-please-config.json`.
2. Add its current version to `.release-please-manifest.json`.
3. Add outputs and a build job to `.github/workflows/release-please.yaml`.
4. Add it to the `image` choice list in `.github/workflows/rebuild-release.yaml`.

## Troubleshooting

**No release PR opened.** release-please only releases directories listed in `release-please-config.json`, and only for commits that touch files inside them. Check the `Release Please` workflow run.

**Release PR is not auto-merging.** Mergify requires the author to be `repo-operator-release-bot[bot]`, the branch to start with `release-please--branches--`, and the PR to touch `.release-please-manifest.json`. All three come from the app token — a `GITHUB_TOKEN` release PR will not satisfy them and will not trigger status checks either.

**A release is stuck as a draft.** The build failed after tagging. Fix the cause, then dispatch `Rebuild Release` for that image and version.

**Renovate shows no release notes for an own image.** The image needs a `sourceDirectory` package rule in `.github/renovate-overrides.json5` pointing at its directory.

[rp]: https://github.com/googleapis/release-please
