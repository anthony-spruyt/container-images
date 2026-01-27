#!/usr/bin/env bash
# shellcheck disable=SC2034 # Variables used by sourcing script (lint.sh)
# Lint configuration - customize per repository
# This file is sourced by lint.sh for both local and CI runs

# MegaLinter Docker image (use digest for reproducibility)
# renovate: TODO
MEGALINTER_IMAGE="ghcr.io/anthony-spruyt/megalinter-container-images@sha256:a96ce561aec6be236738b812fc3aad5ff20d15e648404ca19408b092d37d7e75"

# Skip linting for renovate/dependabot commits in CI
SKIP_BOT_COMMITS=true

# MegaLinter flavor (use "all" for custom images to bypass flavor validation)
MEGALINTER_FLAVOR="all"
