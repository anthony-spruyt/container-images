#!/usr/bin/env bash
set -euo pipefail

# Apply repository rulesets from .github/rulesets/*.json
# Requires: gh CLI authenticated with repo admin permissions

REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RULESETS_DIR="$SCRIPT_DIR/rulesets"

echo "Applying rulesets to $REPO..."

for ruleset in "$RULESETS_DIR"/*.json; do
  if [ -f "$ruleset" ]; then
    name=$(basename "$ruleset" .json)
    echo "  Applying ruleset: $name"

    # Check if ruleset already exists
    existing=$(gh api "repos/$REPO/rulesets" --jq ".[] | select(.name == \"$name\") | .id" 2>/dev/null || true)

    if [ -n "$existing" ]; then
      echo "    Updating existing ruleset (ID: $existing)"
      gh api "repos/$REPO/rulesets/$existing" -X PUT --input "$ruleset"
    else
      echo "    Creating new ruleset"
      gh api "repos/$REPO/rulesets" -X POST --input "$ruleset"
    fi
  fi
done

echo "Done. Rulesets applied successfully."
