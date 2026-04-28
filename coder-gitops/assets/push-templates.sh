#!/bin/bash
# Diff-based Coder template push. For each subdir in TEMPLATES_DIR, pulls the
# active version from Coder, diffs against local files, and only pushes when
# content differs. New templates (pull fails) are always pushed.
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
skipped=()
for dir in "${TEMPLATES_DIR}"/*/; do
  [ -d "$dir" ] || continue
  name="$(basename "$dir")"

  echo "=== Checking template: ${name} ==="

  pull_dir="$(mktemp -d)"
  pull_err="$(mktemp)"

  if coder templates pull "${name}" "${pull_dir}" 2>"${pull_err}"; then
    if diff -rq "${dir}" "${pull_dir}" >/dev/null 2>&1; then
      echo "SKIP: ${name} — no changes detected"
      skipped+=("${name}")
      rm -rf "${pull_dir}" "${pull_err}"
      continue
    fi
    echo "CHANGED: ${name} — pushing new version"
  else
    echo "NEW: ${name} — pull failed ($(head -1 "${pull_err}")), pushing as new template"
  fi

  rm -f "${pull_err}"

  rm -rf "${pull_dir}"

  if coder templates push "${name}" --directory "${dir}" --yes; then
    pushed+=("${name}")
  else
    echo "ERROR: push failed for ${name}" >&2
    failed+=("${name}")
  fi
done

echo
echo "Pushed:  ${#pushed[@]} (${pushed[*]:-none})"
echo "Skipped: ${#skipped[@]} (${skipped[*]:-none})"
echo "Failed:  ${#failed[@]} (${failed[*]:-none})"

[ "${#failed[@]}" -eq 0 ]
