# Chrony NTP Server

Minimal chrony NTP server container designed for Kubernetes deployments with zero Linux capabilities required.

## Features

- Runs as non-root user (uid 1000)
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
      runAsUser: 1000
      runAsGroup: 1000
      runAsNonRoot: true
      allowPrivilegeEscalation: false
      capabilities:
        drop: [ALL]
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

- **No root required**: Runs as uid/gid 1000
- **No capabilities needed**: Uses high port 1123, Kubernetes Service handles 123->1123 mapping
- **No system clock modification**: Uses `-x` flag, chrony only serves time, doesn't adjust host clock
- **Read-only filesystem compatible**: Writes only to `/var/lib/chrony` and `/run/chrony`

## Related

- [spruyt-labs#224](https://github.com/anthony-spruyt/spruyt-labs/issues/224) - Original issue
- [cturra/docker-ntp](https://github.com/cturra/docker-ntp) - Inspiration for environment variables
