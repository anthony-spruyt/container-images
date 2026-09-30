#!/bin/bash
set -euo pipefail

# Local devcontainers get NEXUS_DOCKER_* from --env-file; Coder workspaces leave them unset and mount the cluster config instead.
# Nexus is a mirror, not a location rewrite, so podman falls back to upstream whenever Nexus fails.
[[ -n "${NEXUS_DOCKER_URL:-}" ]] || exit 0

mirror="${NEXUS_DOCKER_URL#http://}"
mirror="${mirror#https://}"
if ! grep -qE '^[a-zA-Z0-9]+([._-][a-zA-Z0-9]+)*(:[0-9]+)?(/[a-zA-Z0-9._/-]*)?$' <<<"${mirror}"; then
  echo "WARNING: NEXUS_DOCKER_URL does not match expected format host[:port][/path] (value redacted), skipping mirror config"
  exit 0
fi

sudo mkdir -p /etc/containers/registries.conf.d
for registry in docker.io ghcr.io quay.io mcr.microsoft.com registry.k8s.io; do
  printf '[[registry]]\nprefix = "%s"\nlocation = "%s"\n\n[[registry.mirror]]\nlocation = "%s"\n\n' \
    "${registry}" "${registry}" "${mirror}"
done | sudo tee /etc/containers/registries.conf.d/99-nexus-mirror.conf >/dev/null

if [[ -z "${NEXUS_DOCKER_USERNAME:-}" || -z "${NEXUS_DOCKER_PASSWORD:-}" ]]; then
  echo "Nexus mirror configured without a login: docker-group rejects anonymous pulls, so podman pulls from upstream"
  exit 0
fi

# Written directly rather than via `podman login`, which needs Nexus up at that moment.
# Rootful podman's default authfile is under /run, which a restart wipes; ~/.config is also on its lookup path.
authfile=/root/.config/containers/auth.json
sudo mkdir -p "$(dirname "${authfile}")"
sudo test -s "${authfile}" || echo '{}' | sudo tee "${authfile}" >/dev/null
sudo install -m 600 /dev/null "${authfile}.new"
printf '%s:%s' "${NEXUS_DOCKER_USERNAME}" "${NEXUS_DOCKER_PASSWORD}" | base64 -w0 |
  sudo jq -Rn --arg host "${mirror%%/*}" --slurpfile cur "${authfile}" '$cur[0] | .auths[$host].auth = input' |
  sudo tee "${authfile}.new" >/dev/null
sudo mv "${authfile}.new" "${authfile}"
echo "Nexus mirror configured with login ${NEXUS_DOCKER_USERNAME}"
