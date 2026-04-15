#!/bin/bash
# Push every Coder template under TEMPLATES_DIR (default /templates).
# Iterates each subdir, runs `coder templates push <name> -y`, continues on
# error, exits non-zero if any failed.
#
# Required env:
#   CODER_URL            - Coder deployment URL (e.g. https://coder.example.com)
#   CODER_SESSION_TOKEN  - Admin session token
# Optional env:
#   TEMPLATES_DIR        - Root dir containing one subdir per template (default /templates)

set -uo pipefail

: "${CODER_URL:?CODER_URL required}"
: "${CODER_SESSION_TOKEN:?CODER_SESSION_TOKEN required}"
TEMPLATES_DIR="${TEMPLATES_DIR:-/templates}"

if [ ! -d "${TEMPLATES_DIR}" ]; then
  echo "ERROR: TEMPLATES_DIR does not exist: ${TEMPLATES_DIR}" >&2
  exit 1
fi

export CODER_URL CODER_SESSION_TOKEN

failed=()
pushed=()
for dir in "${TEMPLATES_DIR}"/*/; do
  [ -d "$dir" ] || continue
  name="$(basename "$dir")"
  echo "=== Pushing template: ${name} ==="
  if coder templates push "${name}" --directory "${dir}" --yes; then
    pushed+=("${name}")
  else
    echo "ERROR: push failed for ${name}" >&2
    failed+=("${name}")
  fi
done

echo
echo "Pushed:  ${#pushed[@]} (${pushed[*]:-none})"
echo "Failed:  ${#failed[@]} (${failed[*]:-none})"

[ "${#failed[@]}" -eq 0 ]
