# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Personal container images, published to `ghcr.io/<owner>/<image>` and `docker.io/aspruyt/<image>`. Container retention only cleans ghcr.io. CI scans each with Trivy and attaches build provenance.

## Commands

```bash
./lint.sh                    # Run MegaLinter locally (exit code 0=pass, non-zero=issues found, results in .output/)
pre-commit run --all-files   # Run pre-commit hooks manually
```

## Adding a New Image

Versions are owned by release-please. See [docs/releases.md](docs/releases.md).

1. Create `<image-name>/Dockerfile`.
2. Register the image in `release-please-config.json` and `.release-please-manifest.json`.
3. Add its outputs and build job to `.github/workflows/release-please.yaml`.
4. Add a `sourceDirectory` rule to `.github/renovate-overrides.json5` so Renovate shows its release notes. `megalinter-*` flavors get theirs in repo-operator's `.github/renovate/package-rules.json5` instead.

### Variant of an existing image (`build_context`)

For a variant that shares another image's sources but needs its own Dockerfile, add a `metadata.yaml` setting `build_context` to that image's directory. The variant directory then only needs a `Dockerfile` (plus optionally `test.sh`) — no copy of the shared `app/` or `assets/`:

```yaml
build_context: llm-guard
```

CI builds with `context: <build_context>` and `file: <image-name>/Dockerfile`, and change detection fans out — a change in the source directory rebuilds the variant too.

Note that release-please only sees the variant's own directory, so a source-only change does not cut a release for the variant. The weekly rebuild covers it; to release immediately, include a commit touching the variant's directory.

### Optional: Add CI Tests

Create `<image-name>/test.sh` - runs after build, before Trivy scan. See `chrony/test.sh` for example.

### Optional: Add Trivy Ignores

Create `<image-name>/.trivyignore` for per-image vulnerability/secret ignores (plain text, one ID per line). Falls back to global `.trivyignore.yaml` if not present.

## Build Triggers

CI never pushes. Every publish goes through release-please — see [docs/releases.md](docs/releases.md).

- **Pull requests**: CI runs on all PRs to main; change detection picks images with modified Dockerfile/top-level `*.sh`/assets/metadata.yaml/flavor.yaml/.rebuild-stamp. PR builds get a read-only token and no secrets, since `test.sh` runs PR code with sudo
- **Push to main**: Lints every push (including xfg sync commits that skip PRs) and builds changed images without pushing (megalinter-factory changes rebuild every flavor)
- **workflow_dispatch**: Manual trigger with an `image` input, for an on-demand build with no push

## Container Retention

Old container images and releases are automatically cleaned up weekly:

- Images older than 4 weeks are deleted
- The weekly run deletes for real; a manual dispatch is a dry run unless `dry_run=false`
- GitHub releases and tags older than 4 weeks are deleted
- 5 most recent versions always kept; draft releases neither count toward the 5 nor get deleted
- The release half aborts before deleting anything if more than 50 releases are planned for deletion (`max_deletions` input on dispatch, 0-999999); the cap counts releases, and each deleted release also removes its tag. It exists because the garbo App bypasses the tag-deletion ruleset
- Runs never overlap (`concurrency` group, no cancel-in-progress)
- Targets: every image registered in `release-please-config.json`
- Workflow: `.github/workflows/container-retention.yaml`, which calls repo-operator's `_container-retention.yaml` with this repo's `GITHUB_TOKEN`. Each package must give this repo the **Admin** role under its Actions access settings (images first pushed by this repo's CI have it)

## Commits

Never commit or push directly to the `main` branch. Always create a feature branch and open a PR unless explicitly told otherwise.

## Linters

Base (`.mega-linter-base.yml`): ACTION_ACTIONLINT, BASH_SHELLCHECK, BASH_SHFMT, JSON_JSONLINT, MARKDOWN_MARKDOWNLINT, REPOSITORY_BETTERLEAKS, REPOSITORY_SECRETLINT, REPOSITORY_TRIVY, SPELL_LYCHEE, YAML_YAMLLINT

Project-specific (`.mega-linter.yml`): DOCKERFILE_HADOLINT

Python: ruff with `pyproject.toml` (extends `ruff-base.toml`), run by MegaLinter as `PYTHON_RUFF` and `PYTHON_RUFF_FORMAT` (this repo lints with `megalinter-python`).

## MegaLinter Flavor Factory

Flavors are named by the languages they lint and shared by every repo with that mix (`megalinter-go`, `megalinter-python`, `megalinter-go-python`). `megalinter-base` (`languages: []`) serves repos with no language to lint. CI generates the Dockerfile at build time.

Each language's linters and toolchain are defined once in `megalinter-factory/languages/<language>.yaml`. `megalinter-factory/base.yaml` holds the linters every flavor gets on top of its upstream base. A flavor lists the languages it combines; never copy a language's linters into a flavor.

### Creating a New MegaLinter Flavor

Only build a flavor when a repo needs that language mix.

1. Create directory: `megalinter-<languages>/`, languages joined by `-`
2. Create `flavor.yaml` listing the languages:

```yaml
---
name: go-python
description: "MegaLinter for Go and Python repositories"

# renovate: datasource=docker depName=ghcr.io/oxsecurity/megalinter-ci_light
upstream_image: "ghcr.io/oxsecurity/megalinter-ci_light:v10.1.0@sha256:..."

languages:
  - go
  - python
```

3. Register it with release-please (see the `create-megalinter-flavor` skill), commit and push

A missing language fails the build. Add one as `languages/<language>.yaml` with `linters` (MegaLinter keys) and, where needed, `extra_dockerfile`, `extra_test_linters`, `extra_test_env_vars`, and `languages` to include another language. Fragments reference their own fields as `{{ language.<field> }}`. A language file is named after a language, never a tool, and holds that language's one linter
set. A flavor may still set `custom_linters` and the `extra_*` fields for something only it needs; these reference `{{ flavor.<field> }}`.

### Version Updates

- **Base image**: Renovate tracks via `# renovate:` annotation in `flavor.yaml`
- **Toolchains and language pins**: Renovate tracks the `# renovate:` annotations in `languages/*.yaml`
- **Linter versions**: Extracted from MegaLinter at build time
- **Weekly rebuild**: Scheduled workflow rebuilds all flavors to pick up new versions

### Releases

Every flavor directory is a release-please package, and `megalinter-factory/` sits outside all of them, so factory and language commits release nothing by themselves. When `base.yaml` or a language definition changes on `main`, `Rebuild MegaLinter Flavors` stamps `.rebuild-stamp` in each flavor that composes it, and that PR releases them. A factory code change that alters generated output needs a
commit touching the affected flavor directories. Details in [docs/releases.md](docs/releases.md#megalinter-flavor-refresh).

### Local Development

```bash
pip install pyyaml jinja2
python megalinter-factory/generate.py megalinter-<name>/
```

Generated files (`Dockerfile`, `test.sh`) are gitignored - CI regenerates at build time.

### Adding Non-Factory Linters

For linters not in MegaLinter upstream, use `extra_dockerfile` for build-time setup and `extra_test_linters` for test verification. Plugin descriptors go in `mega-linter-plugin-<name>/` within the flavor directory and are referenced at runtime via `file:///mega-linter-plugin-<name>/<name>.megalinter-descriptor.yml`. The image bakes `PLUGINS` as an env var default; downstream repos that define
their own `PLUGINS` list must include any baked-in plugin paths alongside their additions. See `megalinter-spruyt-labs/flavor.yaml` for an example using a custom plugin descriptor.

### Factory Files

- `megalinter-factory/generate.py` - Generator script
- `megalinter-factory/compose.py` - Merges base, languages and flavor extras; lists the flavors a changed definition affects
- `megalinter-factory/base.yaml`, `megalinter-factory/languages/` - Linter sets
- `megalinter-factory/megalinter_extractor.py` - Extracts linter info from MegaLinter
- `megalinter-factory/templates/` - Jinja2 templates

## Documentation Style

- Use one representative example per concept — avoid enumerating all current instances to reduce maintenance churn
