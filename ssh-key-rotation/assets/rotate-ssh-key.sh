#!/bin/sh
# Rotate SSH auth + signing keys for a GitHub user account.
#
# Required env:
#   GITHUB_PAT        — PAT with admin:public_key + admin:ssh_signing_key
#   TITLE_PREFIX      — GitHub key title prefix (e.g. "coder-workspace")
#   SECRET_NAME       — Kubernetes secret to patch
#   SECRET_NAMESPACE  — Namespace of that secret
#
# Optional env:
#   FORCE_SYNC_NAMESPACES — comma-separated namespaces for ExternalSecret force-sync
#   FORCE_SYNC_ES_NAME    — ExternalSecret name to sync (required if FORCE_SYNC_NAMESPACES set)

set -e

fail() {
  echo "ERROR: $1" >&2
  exit 1
}

# --- Validate required env vars ---
[ -z "${GITHUB_PAT}" ] && fail "GITHUB_PAT is required"
[ -z "${TITLE_PREFIX}" ] && fail "TITLE_PREFIX is required"
[ -z "${SECRET_NAME}" ] && fail "SECRET_NAME is required"
[ -z "${SECRET_NAMESPACE}" ] && fail "SECRET_NAMESPACE is required"

if [ -n "${FORCE_SYNC_NAMESPACES}" ] && [ -z "${FORCE_SYNC_ES_NAME}" ]; then
  fail "FORCE_SYNC_ES_NAME is required when FORCE_SYNC_NAMESPACES is set"
fi

DATE_SUFFIX=$(date +%Y%m%d)
TITLE="${TITLE_PREFIX}-${DATE_SUFFIX}"

echo "=== SSH key rotation (auth + signing) ==="
echo "Title prefix: ${TITLE_PREFIX}"
echo "Secret: ${SECRET_NAME} in ${SECRET_NAMESPACE}"

# --- Generate new SSH key pair ---
ssh-keygen -t ed25519 -f /tmp/id_ed25519 -N "" -C "${TITLE}"
PUB_KEY=$(cat /tmp/id_ed25519.pub)
echo "New key generated"

# --- Register as AUTHENTICATION key ---
echo "Adding authentication key to GitHub..."
NEW_AUTH_ID=$(curl -s -X POST \
  "https://api.github.com/user/keys" \
  -H "Authorization: token ${GITHUB_PAT}" \
  -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  -d "{\"key\": \"${PUB_KEY}\", \"title\": \"${TITLE}\"}" |
  jq -r '.id')

if [ -z "${NEW_AUTH_ID}" ] || [ "${NEW_AUTH_ID}" = "null" ]; then
  fail "Failed to add authentication key to GitHub"
fi
echo "Authentication key added with ID: ${NEW_AUTH_ID}"

# --- Register as SIGNING key ---
echo "Adding signing key to GitHub..."
NEW_SIGN_ID=$(curl -s -X POST \
  "https://api.github.com/user/ssh_signing_keys" \
  -H "Authorization: token ${GITHUB_PAT}" \
  -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  -d "{\"key\": \"${PUB_KEY}\", \"title\": \"${TITLE}\"}" |
  jq -r '.id')

if [ -z "${NEW_SIGN_ID}" ] || [ "${NEW_SIGN_ID}" = "null" ]; then
  fail "Failed to add signing key to GitHub"
fi
echo "Signing key added with ID: ${NEW_SIGN_ID}"

# --- Clean up old AUTHENTICATION keys ---
echo "Cleaning up old authentication keys..."
curl -s \
  "https://api.github.com/user/keys?per_page=100" \
  -H "Authorization: token ${GITHUB_PAT}" \
  -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2022-11-28" |
  jq -r ".[] | select(.title | startswith(\"${TITLE_PREFIX}-\")) | select(.id != ${NEW_AUTH_ID}) | .id" |
  while read -r OLD_ID; do
    echo "Removing old auth key ID: ${OLD_ID}"
    curl -s -X DELETE \
      "https://api.github.com/user/keys/${OLD_ID}" \
      -H "Authorization: token ${GITHUB_PAT}" \
      -H "Accept: application/vnd.github+json" \
      -H "X-GitHub-Api-Version: 2022-11-28"
  done

# --- Clean up old SIGNING keys ---
echo "Cleaning up old signing keys..."
curl -s \
  "https://api.github.com/user/ssh_signing_keys?per_page=100" \
  -H "Authorization: token ${GITHUB_PAT}" \
  -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2022-11-28" |
  jq -r ".[] | select(.title | startswith(\"${TITLE_PREFIX}-\")) | select(.id != ${NEW_SIGN_ID}) | .id" |
  while read -r OLD_ID; do
    echo "Removing old signing key ID: ${OLD_ID}"
    curl -s -X DELETE \
      "https://api.github.com/user/ssh_signing_keys/${OLD_ID}" \
      -H "Authorization: token ${GITHUB_PAT}" \
      -H "Accept: application/vnd.github+json" \
      -H "X-GitHub-Api-Version: 2022-11-28"
  done

# --- Update Kubernetes secret ---
echo "Updating Kubernetes secret..."
PRIV_KEY=$(base64 -w0 </tmp/id_ed25519)
PUB_KEY_B64=$(printf '%s' "${PUB_KEY}" | base64 -w0)
kubectl patch secret "${SECRET_NAME}" -n "${SECRET_NAMESPACE}" \
  --type='json' \
  -p="[{\"op\": \"replace\", \"path\": \"/data/id_ed25519\", \"value\": \"${PRIV_KEY}\"},{\"op\": \"replace\", \"path\": \"/data/id_ed25519.pub\", \"value\": \"${PUB_KEY_B64}\"}]"

# --- Force-sync ExternalSecrets (optional) ---
if [ -n "${FORCE_SYNC_NAMESPACES}" ]; then
  echo "=== Force-syncing ExternalSecrets ==="
  IFS=','
  # shellcheck disable=SC2086
  set -- ${FORCE_SYNC_NAMESPACES}
  unset IFS
  FAILURES=0
  for NS in "$@"; do
    echo "Force-syncing ${FORCE_SYNC_ES_NAME} in ${NS}..."
    if ! kubectl patch externalsecret "${FORCE_SYNC_ES_NAME}" -n "${NS}" \
      --type='merge' \
      -p="{\"metadata\":{\"annotations\":{\"force-sync\":\"$(date +%s)\"}}}"; then
      echo "WARNING: force-sync in ${NS} failed (non-fatal; ES refreshInterval will recover)"
      FAILURES=$((FAILURES + 1))
    fi
  done
  if [ ${FAILURES} -gt 0 ]; then
    echo "=== Force-sync completed with ${FAILURES} non-fatal failure(s) ==="
  else
    echo "=== Force-sync complete ==="
  fi
fi

# --- Clean up ---
rm -f /tmp/id_ed25519 /tmp/id_ed25519.pub

echo "=== SSH key rotation complete (auth + signing) ==="
