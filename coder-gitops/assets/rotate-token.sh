#!/bin/bash
# Rotate a Coder session token: mint a new token, patch a Kubernetes Secret
# in-place with the new value, then revoke prior tokens with the same name
# prefix.
#
# Required env:
#   CODER_URL              - Coder deployment URL
#   CODER_SESSION_TOKEN    - Admin session token (used to call the API)
#   TOKEN_NAME_PREFIX      - Prefix for minted token names (e.g. "gitops")
#   TOKEN_LIFETIME         - Lifetime accepted by `coder tokens create` (e.g. 720h)
#   SECRET_NAME            - Kubernetes Secret to patch
#   SECRET_NAMESPACE       - Namespace of the Secret
#   SECRET_KEY             - Key inside the Secret to set (e.g. CODER_SESSION_TOKEN)

set -euo pipefail

: "${CODER_URL:?CODER_URL required}"
: "${CODER_SESSION_TOKEN:?CODER_SESSION_TOKEN required}"
: "${TOKEN_NAME_PREFIX:?TOKEN_NAME_PREFIX required}"
: "${TOKEN_LIFETIME:?TOKEN_LIFETIME required}"
: "${SECRET_NAME:?SECRET_NAME required}"
: "${SECRET_NAMESPACE:?SECRET_NAMESPACE required}"
: "${SECRET_KEY:?SECRET_KEY required}"

export CODER_URL CODER_SESSION_TOKEN

DATE_SUFFIX="$(date +%Y%m%d%H%M%S)"
NEW_NAME="${TOKEN_NAME_PREFIX}-${DATE_SUFFIX}"

echo "=== Coder session-token rotation ==="
echo "Minting token: ${NEW_NAME} (lifetime=${TOKEN_LIFETIME})"

NEW_TOKEN="$(coder tokens create --name "${NEW_NAME}" --lifetime "${TOKEN_LIFETIME}")"
if [ -z "${NEW_TOKEN}" ]; then
  echo "ERROR: coder tokens create returned empty value" >&2
  exit 1
fi

echo "Patching secret ${SECRET_NAMESPACE}/${SECRET_NAME} key ${SECRET_KEY}"
NEW_TOKEN_B64="$(printf '%s' "${NEW_TOKEN}" | base64 -w0)"
kubectl patch secret "${SECRET_NAME}" -n "${SECRET_NAMESPACE}" \
  --type='json' \
  -p="[{\"op\":\"replace\",\"path\":\"/data/${SECRET_KEY}\",\"value\":\"${NEW_TOKEN_B64}\"}]"

echo "Revoking prior tokens with prefix ${TOKEN_NAME_PREFIX}-"
coder tokens list --output json |
  jq -r ".[] | select(.token_name | startswith(\"${TOKEN_NAME_PREFIX}-\")) | select(.token_name != \"${NEW_NAME}\") | \"\(.id) \(.token_name)\"" |
  while read -r OLD_ID OLD_NAME; do
    echo "  removing: ${OLD_NAME} (${OLD_ID})"
    coder tokens remove "${OLD_ID}" || echo "  WARN: failed to remove ${OLD_NAME} (${OLD_ID})"
  done

echo "=== Rotation complete ==="
