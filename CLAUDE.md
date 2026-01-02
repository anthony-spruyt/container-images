# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Monorepo for container images published to `ghcr.io/<owner>/<image>`. Images can be built from upstream repos or local Dockerfiles. The workflow builds, tests, scans, and pushes to GHCR.

## Commands

```bash
./lint.sh                    # Run MegaLinter locally (exit code 0=pass, non-zero=issues found, results in .output/)
pre-commit run --all-files   # Run pre-commit hooks manually
./.github/apply-rulesets.sh  # Apply GitHub rulesets (run once after repo creation)
```

## Adding a New Image

### Option 1: From Upstream Source

1. Create `<image-name>/metadata.yaml`:
   ```yaml
   upstream: owner/repo
   version: "1.0.0"
   ```
2. Update workflows:
   - Add upstream to `allowed-upstreams` in `build-and-push.yaml` and `test-pr.yaml`
   - Add to `inputs.image.options` list in `build-and-push.yaml`
3. Add to `.github/dependabot.yml` for base image updates

### Option 2: Local Dockerfile (no upstream)

1. Create `<image-name>/Dockerfile` and `<image-name>/metadata.yaml`:
   ```yaml
   version: "1.0.0"
   ```
2. Update `.github/workflows/build-and-push.yaml`:
   - Add to `inputs.image.options` list (no upstream allowlist needed)
3. Add to `.github/dependabot.yml` for base image updates

### Optional: Add CI Tests

Create `<image-name>/test.sh` - runs after build, before Trivy scan. See `chrony/test.sh` for example.

## Build Triggers

- **Pull requests**: Tests run on PRs when Dockerfile/test.sh/assets/metadata.yaml change
- **Push to main**: Auto-builds on Dockerfile/metadata.yaml changes
- **workflow_dispatch**: Manual trigger with `image` and `version` inputs (used by n8n)

## Commits

Use [Conventional Commits](https://www.conventionalcommits.org/):

```text
<type>(<scope>): <description>

[optional body]
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`, `ci`, `build`

Examples:

- `feat(firemerge): add new image configuration`
- `fix(workflow): correct version validation regex`
- `docs(readme): update setup instructions`
- `ci(lint): add trivy vulnerability scanning`

## Linters (configured in .mega-linter.yml)

ACTION_ACTIONLINT, BASH_SHELLCHECK, MARKDOWN_MARKDOWNLINT, REPOSITORY_GITLEAKS, REPOSITORY_SECRETLINT, REPOSITORY_TRIVY, SPELL_LYCHEE, YAML_YAMLLINT
