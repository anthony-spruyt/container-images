# Chrony NTP Server

Minimal chrony NTP server container designed for Kubernetes deployments with zero Linux capabilities required.

## Features

- Runs entirely as non-root user (uid 1000) - no root required
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
      runAsNonRoot: true
      runAsUser: 1000
      runAsGroup: 1000
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

- **Runs as non-root**: Entire container runs as chrony user (uid 1000), never needs root
- **No capabilities needed**: Uses high port 1123, Kubernetes Service handles 123->1123 mapping
- **No system clock modification**: Uses `-x` flag (see below)
- **Read-only filesystem compatible**: Writes only to `/var/lib/chrony`

### About the `-x` Flag

Chrony operates in two modes:

1. **NTP Client** - Syncs the system clock from upstream servers (requires `SYS_TIME` capability)
2. **NTP Server** - Serves time to clients

With `-x`, chrony:

- ✅ Still syncs its internal time reference from upstream servers
- ✅ Serves accurate time to your NTP clients (IoT devices, etc.)
- ❌ Does NOT modify the host/pod system clock

This is ideal for Kubernetes since nodes have their own time sync. If you need chrony to also adjust the system clock, remove `-x` from `startup.sh`, run as root (`USER root` in Dockerfile), and add `SYS_TIME` capability.

## n8n Release Watcher

The `n8n-release-watcher.json` workflow automatically detects new chrony package versions in Alpine Linux and triggers a container build.

### What it does

1. Checks daily (midnight UTC) for chrony package updates in Alpine Linux
2. Dynamically reads the Alpine version from this repo's Dockerfile
3. Fetches the corresponding APKBUILD from Alpine's Git repository
4. Compares the package version with the last processed version (stored in workflow static data)
5. If a new version is found:
   - Triggers the container build workflow
   - Sends an email notification
   - Updates the stored version

### Import into n8n

1. In n8n, go to **Workflows** > **Add Workflow** > **Import from File**
2. Select `n8n-release-watcher.json`
3. Configure the credentials (see below)
4. Activate the workflow

### Required Credentials

#### 1. GitHub Personal Access Token (Header Auth)

Create a GitHub PAT with `repo` and `workflow` scopes:

1. Go to GitHub > Settings > Developer settings > Personal access tokens > Fine-grained tokens
2. Create a new token with:
   - **Repository access:** `anthony-spruyt/container-images`
   - **Permissions:** Actions (Read and write)
3. In n8n, go to **Credentials** > **Add Credential** > **Header Auth**
4. Configure:
   - **Name:** `GitHub PAT`
   - **Header Name:** `Authorization`
   - **Header Value:** `Bearer <your-token>`

#### 2. SMTP Credential

1. In n8n, go to **Credentials** > **Add Credential** > **SMTP**
2. Configure your SMTP server settings:
   - **Host:** Your SMTP server hostname
   - **Port:** 587 (TLS) or 465 (SSL)
   - **User:** Your SMTP username
   - **Password:** Your SMTP password
   - **SSL/TLS:** Enable as required

### Configuration After Import

1. Open the **Trigger Build Workflow** node and select your GitHub PAT credential
2. Open the **Send Notification** node:
   - Select your SMTP credential
   - Update `fromEmail` to your sender address
   - Update `toEmail` to your notification recipient
3. Save and activate the workflow

### Testing

1. Open the workflow in n8n
2. Click **Execute Workflow** to run manually
3. Check the output of each node:
   - **Get Dockerfile:** Should return Dockerfile content
   - **Parse Alpine Version:** Shows extracted Alpine version (e.g., `3.23`)
   - **Get Alpine APKBUILD:** Should return APKBUILD content
   - **Check New Version:** Shows `isNew: true` on first run
   - **Trigger Build Workflow:** Should return HTTP 204 (success)
   - **Send Notification:** Sends email to configured recipient

On subsequent runs, `isNew` will be `false` until Alpine updates the chrony package.

## Related

- [spruyt-labs#224](https://github.com/anthony-spruyt/spruyt-labs/issues/224) - Original issue
- [cturra/docker-ntp](https://github.com/cturra/docker-ntp) - Inspiration for environment variables
