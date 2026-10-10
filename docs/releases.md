# Releases

Image versions live in `.release-please-manifest.json`. [release-please][rp] owns them: it opens one release PR covering every image with pending changes, and merging that PR creates a tag and a **draft** release for each of them. The image is built and pushed from the tag, and only then is the release published. A published release always has an image behind it.

## Tag format

A release tags `<image>-<version>` and pushes the docker tags `<version>`, `<major>.<minor>`, and `latest`:

```text
chrony-5.0.4                    -> 5.0.4, 5.0, latest
megalinter-spruyt-labs-v3.0.0   -> v3.0.0, v3.0, latest
```

Git tags keep the format this repo already used, so existing tags round-trip and release-please finds them as version anchors. Some images carry a `v` before the version and some do not; that inconsistency is preserved deliberately because downstream repos pin the docker tags. Whether a given image takes the `v` is set by `include-v-in-tag` in `release-please-config.json`.

## How a release happens

1. You merge a conventional commit that touches an image directory.
2. `Release Please` runs on `main` and opens (or updates) a single release PR, labelled `autorelease: pending`, covering every image with pending changes.
3. Mergify auto-merges the release PR once `summary / Check Results` passes.
4. Merging creates a git tag and a **draft** GitHub release per image in the PR.
5. The same workflow run builds each released image from the commit the run started from, runs its `test-command`, pushes it to `ghcr.io/anthony-spruyt/<image>` and `docker.io/aspruyt/<image>`, attests provenance, and publishes that image's release with the ref and digest appended. A matrix job runs once per released image, so one PR still yields one tag, release, and build per image.

If step 5 fails, the release stays a draft and no image is published. See [Recovering a stuck draft](#recovering-a-stuck-draft).

### The build is always the tag's commit

The image job checks out the commit its run started from (`github.sha`), never the tag by name, and refuses to build unless the release tag points at that commit. The provenance attestation always names the run's commit and no input overrides it, so building any other commit would sign the wrong source. The `org.opencontainers.image.revision` label comes from the checked-out commit (`docker/metadata-action` `context: git`), so it matches too. release-please tags the release PR's merge commit, which is the commit its run starts from, so on the normal path the check passes.

A push to `main` while a `Release Please` run is still pending makes GitHub cancel that run. If the cancelled run was the release PR's merge, the next run's release-please creates the release for the earlier merge commit, and its image job refuses: the run fails, the release stays a draft, and the error says to cut the next release and then delete the draft.

The image job checks the release before building and fails closed:

- release lookup fails (missing tag, API error, token that can't see drafts): the job fails and the release stays a draft
- release is a draft: build, push, attest, publish
- release is already published: skip the build and leave the release unchanged, so an overlapping run can't push again or append a second image section
- any other answer: the job fails

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

On a PR, CI's `image` job builds each changed image through repo-operator's shared `_images.yaml` without pushing. Nothing is pushed and no release is touched. The image's `test-command` from its `metadata.yaml` runs against the locally loaded image; a `test.sh` that no `test-command` names never runs.

That job runs PR code with sudo, so it gets `contents: read` and no secrets. Only the release workflows publish, and only they get write scopes and `DOCKERHUB_TOKEN`, which they pass explicitly, never with `secrets: inherit`. See repo-operator's [docs/ci.md](https://github.com/anthony-spruyt/repo-operator/blob/main/docs/ci.md#images) for change detection.

## MegaLinter flavor refresh

Flavor linter versions are resolved at build time, so a flavor only needs a reason to rebuild. `Rebuild MegaLinter Flavors` gives it one by writing `megalinter-<name>/.rebuild-stamp` and opening one PR. Mergify merges it, release-please cuts a `chore` patch release per stamped flavor, and the images rebuild.

It runs:

- **Weekly**, stamping every flavor with today's date.
- **On a push to `main` that modifies `megalinter-factory/base.yaml` or `megalinter-factory/languages/*.yaml`**, stamping only the flavors that compose the changed file, with `<date>-<sha>`.
  The factory is not a release-please package, so a language or toolchain change (such as Renovate moving `go_image`) releases flavors only through this PR. Newly added definitions stamp nothing until a flavor lists them, and flavors whose stamp the push already changed are skipped.

Runs are serialized. If a refresh PR is still open, the new run stamps its flavors as well and closes it as superseded, so two refresh PRs never edit the same stamp.

The job runs in the `release` environment, which holds the App credentials (`RELEASE_PLEASE_APP_CLIENT_ID`, `RELEASE_PLEASE_APP_PRIVATE_KEY`) and admits only `main`. The schedule, push and manual triggers all run there; the workflow has no pull request trigger.

A factory code change that alters generated output releases nothing by itself; include a commit that touches the affected flavor directories. A `build:` commit to a flavor directory releases nothing either, since `build` has no changelog section — use it for changes that leave the generated image unchanged.

A change that removes or replaces a linter breaks consumers that enable it, so it must release the affected flavors as a major from the change itself, not as a refresh `chore` patch.
Change each affected flavor's `.rebuild-stamp` in the same PR, keep every other flavor directory out of it, and title the PR `<type>(<scope>)!: <what consumers must change>`. The refresh then skips the flavors the PR stamped.
A squash merge here takes its subject from the commit when the PR has only one, otherwise from the PR title, and its body from the commit messages, never the PR body. So put the `!` in that subject (the commit's own for a one-commit PR), or a `BREAKING CHANGE:` footer in a commit message.

### Removal guard

The `Guard Linter Removals` check (`.github/workflows/removal-guard.yaml`) enforces this on every PR. `megalinter-factory/removal_guard.py` composes every flavor on `main` and on the PR. If a flavor present on both sides loses a linter, the check fails unless:

- the squash subject has `!`, or a commit has a `BREAKING CHANGE:` footer, and
- the PR changes the `.rebuild-stamp` of every flavor that loses a linter and touches no other flavor directory. The stamp, not just any file, is what makes the refresh skip the flavor.

It compares composed linter sets (base, languages and `custom_linters`), not upstream image changes. New and deleted flavors are not removals. The check also runs when the PR is edited, outside the rest of CI, so dropping the `!` from the title after a green run fails it again.

## Variant images

`llm-guard-cuda` builds from `llm-guard/` via `build_context`, but release-please only watches `llm-guard-cuda/`'s own path. A change confined to `llm-guard/app/` therefore releases `llm-guard` but not the CUDA variant. The CUDA variant picks the change up on its next release; to ship it immediately, include a commit that touches `llm-guard-cuda/`.

## Recovering a stuck draft

A release that was tagged but whose build failed stays a draft. How to recover depends on the cause:

- **The cause is outside the commit and outside the pinned shared workflows** (a registry outage, a flaky test, a missing or expired secret): fix the cause, then re-run the release run's failed jobs. A re-run uses the same commit and the same pinned `_release-please.yaml`, so it publishes the draft whenever that commit is the tag.

  ```bash
  gh run rerun <run-id> --failed
  ```

- **The tagged code is broken, or the cause is in repo-operator's shared workflows:** fix it on `main` (for a shared workflow, the fix lands once the caller pin moves) and cut the next release, then delete the leftover draft.
- **The tag points at a different commit than the run** (for example, after a cancelled run): cut the next release, then delete the leftover draft.

A full re-run does not help: release-please does not re-emit `releases_created` on a second pass, so the build job is skipped.

## Configuration

| File                                    | Purpose                                                 |
| --------------------------------------- | ------------------------------------------------------- |
| `release-please-config.json`            | Per-image release type, component, and tag format       |
| `.release-please-manifest.json`         | Current version per image — the source of truth         |
| `<image>/metadata.yaml`                 | Per-image build settings, such as `test-command`        |
| `.github/workflows/release-please.yaml` | Synced caller of repo-operator's `_release-please.yaml` |

Notable settings:

| Setting              | Why                                                          |
| -------------------- | ------------------------------------------------------------ |
| `always-update`      | Keeps the open release PR current as commits land            |
| `draft`              | The release is published only after the image is pushed      |
| `force-tag-creation` | Creates the tag alongside the draft release                  |
| `tag-separator: "-"` | Matches the tags this repo already uses, so they round-trip  |
| `include-v-in-tag`   | Per image. Preserves each image's existing `v`-or-not prefix |
| `last-release-sha`   | Bounds history scanning — see below                          |

### `last-release-sha`

This repo has over 400 tags and releases. Release-please pages through them looking for each component's anchor and can give up before reaching one, then walks the full history instead — which surfaces years-old `feat:` commits and cuts a **minor** bump where a patch was correct.

`last-release-sha` bounds that walk, so each image considers only commits after it.

Leave it in place. It is not migration scaffolding, and removing it silently inflates version bumps.

## Adding an image

1. Add the directory to `packages` in `release-please-config.json`.
2. Add its current version to `.release-please-manifest.json`.
3. Add `<image>/metadata.yaml`. Set `test-command` if the image has a `test.sh`; nothing runs it otherwise. The release workflows find the image in `release-please-config.json` and take the docker tag's `v` prefix from `include-v-in-tag`, so they need no change.
4. Add a `sourceDirectory` rule so Renovate shows its release notes: in `renovate-overrides.json5`, or for a `megalinter-*` flavor in repo-operator's `.github/renovate/package-rules.json5`, which every repo extends.
5. Ask for the image to be added to `retentionPackages` in repo-operator's `src/repos.yaml`, which writes the synced `container-retention.yaml`.

## Troubleshooting

**No release PR opened.** release-please only releases directories listed in `release-please-config.json`, and only for commits that touch files inside them. Check the `Release Please` workflow run.

**Release PR is not auto-merging.** Mergify requires the author to be `repo-operator-release-bot[bot]`, the branch to start with `release-please--branches--`, and the PR to touch `.release-please-manifest.json`. All three come from the app token — a `GITHUB_TOKEN` release PR will not satisfy them and will not trigger status checks either.

**A release is stuck as a draft.** The build failed after tagging. See [Recovering a stuck draft](#recovering-a-stuck-draft).

**Renovate shows no release notes for an own image.** The image needs a `sourceDirectory` package rule pointing at its directory, in `renovate-overrides.json5` (or repo-operator's `.github/renovate/package-rules.json5` for a `megalinter-*` flavor).

[rp]: https://github.com/googleapis/release-please
