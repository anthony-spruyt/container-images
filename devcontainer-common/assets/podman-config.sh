#!/bin/bash
set -euo pipefail

DROPIN=/etc/containers/containers.conf.d/50-host-namespaces.conf

# Without CAP_SYS_ADMIN (WSL) podman cannot create net/UTS namespaces; bit 21 is that cap.
cap_bnd=$(awk '/^CapBnd:/ {print $2}' /proc/self/status)
if (((0x$cap_bnd >> 21) & 1)); then
  sudo rm -f "$DROPIN"
  exit 0
fi

sudo mkdir -p "$(dirname "$DROPIN")"
sudo tee "$DROPIN" >/dev/null <<'CONF'
[containers]
netns = "host"
utsns = "host"
CONF
