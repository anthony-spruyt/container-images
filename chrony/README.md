# Chrony NTP Server

Minimal chrony NTP server container designed for Kubernetes deployments with zero Linux capabilities required.

## Features

- Starts as root, drops to non-root user (uid 1000) after initialization
- Listens on high port 1123 (no NET_BIND_SERVICE capability needed)
- Zero capabilities required
- NTS (Network Time Security) support
- Alpine-based, minimal footprint

## Usage

### Docker

```bash
docker run -d \
  --name chrony \
  -p 123:1123/udp \
  -e NTP_SERVERS="time.cloudflare.com" \
  -e ENABLE_NTS="true" \
  ghcr.io/anthony-spruyt/chrony:latest
```

### Kubernetes

```yaml
containers:
  - name: chrony
    image: ghcr.io/anthony-spruyt/chrony:latest
    securityContext:
      allowPrivilegeEscalation: false
      capabilities:
        drop: [ALL]
      # Note: Container starts as root but chronyd drops to uid 1000
      # runAsNonRoot: false is implicit
    ports:
      - containerPort: 1123
        protocol: UDP
    env:
      - name: NTP_SERVERS
        value: "time.cloudflare.com"
      - name: ENABLE_NTS
        value: "true"
---
apiVersion: v1
kind: Service
metadata:
  name: chrony
spec:
  ports:
    - port: 123
      targetPort: 1123
      protocol: UDP
```

## Environment Variables

| Variable      | Default               | Description                                                 |
| ------------- | --------------------- | ----------------------------------------------------------- |
| `NTP_SERVERS` | `time.cloudflare.com` | Comma-separated list of upstream NTP servers                |
| `NTP_PORT`    | `1123`                | Port for chronyd to listen on                               |
| `ENABLE_NTS`  | `false`               | Enable Network Time Security (all servers must support NTS) |
| `LOG_LEVEL`   | `0`                   | Logging verbosity: 0=info, 1=warn, 2=error, 3=fatal         |
| `NOCLIENTLOG` | `false`               | Disable logging of client requests                          |
| `TZ`          | `UTC`                 | Container timezone                                          |

## Security

This image is designed for minimal privilege operation:

- **Drops privileges after init**: Starts as root for socket setup, then drops to uid 1000
- **No capabilities needed**: Uses high port 1123, Kubernetes Service handles 123->1123 mapping
- **No system clock modification**: Uses `-x` flag (see below)
- **Read-only filesystem compatible**: Writes only to `/var/lib/chrony` and `/run/chrony`

### About the `-x` Flag

Chrony operates in two modes:

1. **NTP Client** - Syncs the system clock from upstream servers (requires `SYS_TIME` capability)
2. **NTP Server** - Serves time to clients

With `-x`, chrony:

- ✅ Still syncs its internal time reference from upstream servers
- ✅ Serves accurate time to your NTP clients (IoT devices, etc.)
- ❌ Does NOT modify the host/pod system clock

This is ideal for Kubernetes since nodes have their own time sync. If you need chrony to also adjust the system clock, remove `-x` from `startup.sh` and add `SYS_TIME` capability.

## Related

- [spruyt-labs#224](https://github.com/anthony-spruyt/spruyt-labs/issues/224) - Original issue
- [cturra/docker-ntp](https://github.com/cturra/docker-ntp) - Inspiration for environment variables
