# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Monorepo for container images published to `ghcr.io/<owner>/<image>`. Each image directory contains `metadata.yaml` referencing an upstream repo. The workflow clones upstream, builds, and pushes to GHCR.

## Commands

```bash
./lint.sh                    # Run MegaLinter locally (output in .output/)
pre-commit run --all-files   # Run pre-commit hooks manually
./.github/apply-rulesets.sh  # Apply GitHub rulesets (run once after repo creation)
```

## Adding a New Image

1. Create `<image-name>/metadata.yaml`:
   ```yaml
   upstream: owner/repo
   version: "1.0.0"
   ```
2. Update `.github/workflows/build-and-push.yaml`:
   - Add to `ALLOWED_UPSTREAMS` env var
   - Add to `inputs.image.options` list

## Build Triggers

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
