# Releases

Image versions live in `.release-please-manifest.json`. [release-please][rp] owns them: it opens a release PR per image, and merging that PR creates the tag and a **draft** release. The image is built and pushed from the tag, and only then is the release published. A published release always has an image behind it.

## Images

| Image                       | Git tag                                | Docker tag                    |
| --------------------------- | -------------------------------------- | ----------------------------- |
| chrony                      | `chrony-5.0.0`                         | `5.0.0`, `5.0`, `latest`      |
| claude-agent-read           | `claude-agent-read-1.0.81`             | `1.0.81`, `1.0`, `latest`     |
| claude-agent-spruyt-labs    | `claude-agent-spruyt-labs-1.0.80`      | `1.0.80`, `1.0`, `latest`     |
| claude-agent-write          | `claude-agent-write-1.0.73`            | `1.0.73`, `1.0`, `latest`     |
| coder-gitops                | `coder-gitops-1.0.22`                  | `1.0.22`, `1.0`, `latest`     |
| devcontainer-common         | `devcontainer-common-1.2.34`           | `1.2.34`, `1.2`, `latest`     |
| llm-guard                   | `llm-guard-1.0.33`                     | `1.0.33`, `1.0`, `latest`     |
| llm-guard-cuda              | `llm-guard-cuda-1.0.7`                 | `1.0.7`, `1.0`, `latest`      |
| megalinter-container-images | `megalinter-container-images-v10.0.52` | `v10.0.52`, `v10.0`, `latest` |
| megalinter-firemerge        | `megalinter-firemerge-1.0.19`          | `1.0.19`, `1.0`, `latest`     |
| megalinter-spruyt-labs      | `megalinter-spruyt-labs-v1.0.36`       | `v1.0.36`, `v1.0`, `latest`   |
| megalinter-sungather        | `megalinter-sungather-1.0.19`          | `1.0.19`, `1.0`, `latest`     |
| megalinter-xfg              | `megalinter-xfg-v1.0.45`               | `v1.0.45`, `v1.0`, `latest`   |
| ssh-key-rotation            | `ssh-key-rotation-2.0.5`               | `2.0.5`, `2.0`, `latest`      |

Git tags keep the format this repo already used, so existing tags round-trip and release-please finds them as version anchors. Some images carry a `v` before the version and some do not; that inconsistency is preserved deliberately because downstream repos pin the docker tags.

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

## Weekly MegaLinter flavor refresh

Flavor linter versions are resolved at build time, so a flavor only needs a reason to rebuild. `Rebuild MegaLinter Flavors` runs weekly and writes today's date to `megalinter-<name>/.rebuild-stamp`, then opens one PR. Mergify merges it, release-please cuts a `chore` patch release per flavor, and the images rebuild.

## Variant images

`llm-guard-cuda` builds from `llm-guard/` via `build_context`, but release-please only watches `llm-guard-cuda/`'s own path. A change confined to `llm-guard/app/` therefore releases `llm-guard` but not the CUDA variant. The CUDA variant picks the change up on its next release; to ship it immediately, include a commit that touches `llm-guard-cuda/`.

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

| Setting                  | Why                                                          |
| ------------------------ | ------------------------------------------------------------ |
| `separate-pull-requests` | One release PR per image                                     |
| `always-update`          | Keeps sibling release PRs from conflicting on the manifest   |
| `draft`                  | The release is published only after the image is pushed      |
| `force-tag-creation`     | Creates the tag alongside the draft release                  |
| `tag-separator: "-"`     | Matches the tags this repo already uses, so they round-trip  |
| `include-v-in-tag`       | Per image. Preserves each image's existing `v`-or-not prefix |
| `last-release-sha`       | Bounds history scanning — see below                          |

### `last-release-sha`

This repo has over 400 tags and releases. Release-please pages through them looking for each component's anchor and can give up before reaching one, then walks the full history instead — which surfaces years-old `feat:` commits and cuts a **minor** bump where a patch was correct.

`last-release-sha` bounds that walk, so each image considers only commits after it.

Leave it in place. It is not migration scaffolding, and removing it silently inflates version bumps.

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
