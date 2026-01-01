#!/usr/bin/env bash
set -euo pipefail

# Runs mega-linter against the repository.
# Can be run from any directory.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

rm -rf "$REPO_ROOT/.output"
mkdir "$REPO_ROOT/.output"

docker run \
  -a STDOUT \
  -a STDERR \
  -u "$(id -u):$(id -g)" \
  -w /tmp/lint \
  -e HOME=/tmp \
  -e APPLY_FIXES="all" \
  -e UPDATED_SOURCES_REPORTER="true" \
  -e REPORT_OUTPUT_FOLDER="/tmp/lint/.output" \
  -v "$REPO_ROOT:/tmp/lint" \
  --rm \
  ghcr.io/oxsecurity/megalinter-documentation@sha256:c2f426be556c45c8ca6ca4bccb147160711531c698362dd0a05918536fc022bf # v9.2.0

# Capture MegaLinter exit code
LINT_EXIT_CODE=$?

# Copy fixed files back to workspace
if compgen -G "$REPO_ROOT/.output/updated_sources/*" > /dev/null; then
    cp -r "$REPO_ROOT/.output/updated_sources"/* "$REPO_ROOT/"
fi

exit $LINT_EXIT_CODE
