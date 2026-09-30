#!/bin/bash
set -euo pipefail

# Local devcontainers get NEXUS_DOCKER_* from --env-file; Coder workspaces leave them unset and mount the cluster config instead.
# Nexus is a mirror, not a location rewrite, so podman falls back to upstream whenever Nexus fails.
[[ -n "${NEXUS_DOCKER_URL:-}" ]] || exit 0

mirror="${NEXUS_DOCKER_URL%$'\r'}"
mirror="${mirror#http://}"
mirror="${mirror#https://}"
if ! grep -qE '^[a-zA-Z0-9]+([._-][a-zA-Z0-9]+)*(:[0-9]+)?(/[a-zA-Z0-9._/-]*)?$' <<<"${mirror}"; then
  echo "WARNING: NEXUS_DOCKER_URL does not match expected format host[:port][/path] (value redacted), skipping mirror config"
  exit 0
fi
host="${mirror%%/*}"

sudo mkdir -p /etc/containers/registries.conf.d
for registry in docker.io ghcr.io quay.io mcr.microsoft.com registry.k8s.io; do
  printf '[[registry]]\nprefix = "%s"\nlocation = "%s"\n\n[[registry.mirror]]\nlocation = "%s"\n\n' \
    "${registry}" "${registry}" "${mirror}"
done | sudo tee /etc/containers/registries.conf.d/99-nexus-mirror.conf >/dev/null

# .env files edited on Windows carry CRLF, and --env-file keeps the \r.
user="${NEXUS_DOCKER_USERNAME:-}"
user="${user%$'\r'}"
pass="${NEXUS_DOCKER_PASSWORD:-}"
pass="${pass%$'\r'}"
auth=""
if [[ "${user}" == *:* ]]; then
  echo "WARNING: NEXUS_DOCKER_USERNAME must not contain ':'; configuring Nexus mirror without a login"
elif [[ -n "${user}" && -n "${pass}" ]]; then
  auth="$(printf '%s:%s' "${user}" "${pass}" | base64 -w0)"
else
  if [[ -n "${user}${pass}" ]]; then
    echo "WARNING: set both NEXUS_DOCKER_USERNAME and NEXUS_DOCKER_PASSWORD; configuring Nexus mirror without a login"
  else
    echo "Nexus mirror configured without a login: docker-group rejects anonymous pulls, so podman pulls from upstream"
  fi
fi

# Not `podman login` (needs Nexus up) and not its /run default (wiped on restart); podman also reads this path.
# managedBy marks our entries so a host change or cleared login removes them.
authfile=/root/.config/containers/auth.json
[[ -n "${auth}" ]] || sudo test -e "${authfile}" || exit 0
cur="$(sudo cat "${authfile}" 2>/dev/null || true)"
[[ -n "${cur//[[:space:]]/}" ]] || cur="{}"
# The credential goes through env, never argv, so it stays out of ps and sudo logs.
if ! new="$(NEXUS_AUTH="${auth}" jq -e --arg host "${host}" '
  if type != "object" then error("not an object") else . end
  | .auths = ((.auths // {}) | with_entries(select(.value.managedBy? != "devcontainer-nexus-config")))
  | if env.NEXUS_AUTH == "" then . else .auths[$host] = {auth: env.NEXUS_AUTH, managedBy: "devcontainer-nexus-config"} end' \
  <<<"${cur}" 2>/dev/null)"; then
  echo "WARNING: ${authfile} is not a JSON object; left it unchanged, so the Nexus login was not written"
  exit 0
fi
sudo mkdir -p "$(dirname "${authfile}")"
printf '%s\n' "${new}" | sudo sh -c 'umask 077 && cat >"$1.new" && mv "$1.new" "$1"' _ "${authfile}"
[[ -z "${auth}" ]] || echo "Nexus mirror configured with login ${user}"
