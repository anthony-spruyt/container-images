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

Create `<image-name>/metadata.yaml`:

```yaml
upstream: owner/repo
version: "1.0.0"
```

### Option 2: Local Dockerfile (no upstream)

Create `<image-name>/Dockerfile` and `<image-name>/metadata.yaml`:

```yaml
version: "1.0.0"
```

### That's It

- **No workflow updates needed** - upstream validation uses each image's own `metadata.yaml`
- **Dependabot auto-generated** - pre-commit hook updates `.github/dependabot.yml` automatically

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
