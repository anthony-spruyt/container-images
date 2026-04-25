# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Container images built from upstream sources or custom Dockerfiles, published to `ghcr.io/<owner>/<image>` with automated security scanning and SLSA provenance.

## Commands

```bash
./lint.sh                    # Run MegaLinter locally (exit code 0=pass, non-zero=issues found, results in .output/)
pre-commit run --all-files   # Run pre-commit hooks manually
```

## Adding a New Image

### Option 1: From Upstream Source

Create `<image-name>/metadata.yaml`:

```yaml
upstream: owner/repo
# renovate: datasource=github-tags depName=owner/repo
version: "1.0.0"
```

The Renovate annotation enables automatic version tracking. Supported datasources:

- `github-tags` - GitHub repository tags
- `github-releases` - GitHub releases
- `docker` - Docker Hub or container registries

### Option 2: Local Dockerfile (no upstream)

Create `<image-name>/Dockerfile` and `<image-name>/metadata.yaml`:

```yaml
version: "1.0.0"
```

### Option 3: Auto-patched version (no upstream)

For images where CI should auto-increment the patch version on each build, specify only the base version and set `auto_patch: true`:

```yaml
version: "1.1"
auto_patch: true
```

CI appends `.N` automatically (e.g., `1.1.0`, `1.1.1`, `1.1.2`). Do **not** include the patch segment in `version` — writing `"1.1.0"` with `auto_patch: true` would produce `1.1.0.0`.

### That's It

- **No workflow updates needed** - upstream validation uses each image's own `metadata.yaml`
- **Renovate tracking** - add `# renovate:` annotations to `metadata.yaml` for automatic version updates

### Optional: Add CI Tests

Create `<image-name>/test.sh` - runs after build, before Trivy scan. See `chrony/test.sh` for example.

### Optional: Add Trivy Ignores

Create `<image-name>/.trivyignore` for per-image vulnerability/secret ignores (plain text, one ID per line). Falls back to global `.trivyignore.yaml` if not present.

### Optional: n8n Release Watcher (for non-standard sources)

For upstream sources that Renovate cannot monitor (e.g., Alpine packages), use n8n workflows. See `chrony/n8n-release-watcher.json` for an example that monitors Alpine package versions.

## Build Triggers

- **Pull requests**: CI runs on all PRs to main; change detection picks images with modified Dockerfile/test.sh/assets/metadata.yaml/flavor.yaml
- **Push to main**: Auto-builds on Dockerfile/metadata.yaml/flavor.yaml/assets changes (also triggers on megalinter-factory or CI script changes)
- **workflow_dispatch**: Manual trigger with `image`, `version`, and `dry_run` inputs

## Container Retention

Old container images and releases are automatically cleaned up weekly:

- Images older than 4 weeks are deleted
- GitHub releases and tags older than 4 weeks are deleted
- 5 most recent versions always kept
- Targets: `megalinter-*`
- Workflow: `.github/workflows/container-retention.yaml`

## Commits

Never commit or push directly to the `main` branch. Always create a feature branch and open a PR unless explicitly told otherwise.

## Linters

Base (`.mega-linter-base.yml`): ACTION_ACTIONLINT, BASH_SHELLCHECK, BASH_SHFMT, JSON_JSONLINT, MARKDOWN_MARKDOWNLINT, REPOSITORY_GITLEAKS, REPOSITORY_SECRETLINT, REPOSITORY_TRIVY, SPELL_LYCHEE, YAML_YAMLLINT

Project-specific (`.mega-linter.yml`): DOCKERFILE_HADOLINT, PYTHON_PYLINT

## MegaLinter Flavor Factory

Create custom MegaLinter flavors by defining a `flavor.yaml` configuration. CI generates Dockerfile at build time.

### Creating a New MegaLinter Flavor

1. Create directory: `megalinter-<name>/`
1. Create `flavor.yaml` - just list the linter keys you want:

```yaml
name: my-flavor
description: "Custom MegaLinter for my use case"

# renovate: datasource=docker depName=oxsecurity/megalinter-ci_light
upstream_image: "oxsecurity/megalinter-ci_light:v9.3.0@sha256:..."

# Just list linter keys - versions extracted from MegaLinter automatically
custom_linters:
  - ACTION_ACTIONLINT
  - SPELL_LYCHEE
  - MARKDOWN_MARKDOWNLINT
```

3. Commit and push - CI generates all files and builds automatically

### Version Updates

- **Base image**: Renovate tracks via `# renovate:` annotation in `flavor.yaml`
- **Linter versions**: Extracted from MegaLinter at build time - zero maintenance
- **Weekly rebuild**: Scheduled workflow rebuilds all flavors to pick up new versions

### Local Development

```bash
pip install pyyaml jinja2
python megalinter-factory/generate.py megalinter-<name>/
```

Generated files (`Dockerfile`, `test.sh`) are gitignored - CI regenerates at build time.

### Factory Files

- `megalinter-factory/generate.py` - Generator script
- `megalinter-factory/megalinter_extractor.py` - Extracts linter info from MegaLinter
- `megalinter-factory/templates/` - Jinja2 templates

## Documentation Style

- Use one representative example per concept — avoid enumerating all current instances to reduce maintenance churn
