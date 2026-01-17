# SunGather Container Image

Python tool that collects data from Sungrow Inverters using ModbusTcpClient and exports to various platforms.

- **Upstream:** <https://github.com/anthony-spruyt/SunGather>
- **Container:** `ghcr.io/anthony-spruyt/sungather`

## Features

- ModbusTCP communication with Sungrow inverters
- Automatic model detection and register configuration
- Multiple export formats:
  - Console logging
  - Webserver (HTTP endpoint on port 8080)
  - MQTT with Home Assistant auto-discovery
  - InfluxDB metrics
  - Prometheus exporter
  - PVOutput integration
- Multi-architecture support (amd64, arm64)

## Usage

### Docker

```bash
docker run -d \
  --name sungather \
  --restart always \
  -v /path/to/config.yaml:/config/config.yaml \
  -v /path/to/logs:/logs \
  -e TZ=America/New_York \
  -p 8080:8080 \
  ghcr.io/anthony-spruyt/sungather:v0.5.3
```

### Kubernetes

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: sungather-config
data:
  config.yaml: |
    # See https://github.com/anthony-spruyt/SunGather/blob/master/config-example.yaml
    inverter:
      host: "192.168.1.100"
      port: 502
      scan_interval: 30
    exports:
      - name: webserver
        enabled: true
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: sungather
spec:
  replicas: 1
  selector:
    matchLabels:
      app: sungather
  template:
    metadata:
      labels:
        app: sungather
    spec:
      containers:
        - name: sungather
          image: ghcr.io/anthony-spruyt/sungather:v0.5.3
          ports:
            - containerPort: 8080
              name: http
          env:
            - name: TZ
              value: "America/New_York"
          volumeMounts:
            - name: config
              mountPath: /config
            - name: logs
              mountPath: /logs
      volumes:
        - name: config
          configMap:
            name: sungather-config
        - name: logs
          emptyDir: {}
---
apiVersion: v1
kind: Service
metadata:
  name: sungather
spec:
  ports:
    - port: 8080
      targetPort: 8080
      name: http
  selector:
    app: sungather
```

## Configuration

SunGather requires a `config.yaml` file. See the [upstream config-example.yaml](https://github.com/anthony-spruyt/SunGather/blob/master/SunGather/config-example.yaml) for all available options.

**Minimum configuration:**

```yaml
inverter:
  host: "192.168.1.100" # Your inverter IP
  port: 502 # Modbus TCP port
  scan_interval: 30 # Seconds between scans

exports:
  - name: console
    enabled: true
```

## Environment Variables

| Variable | Default | Description                                   |
| -------- | ------- | --------------------------------------------- |
| `TZ`     | UTC     | Container timezone (e.g., "America/New_York") |

## Ports

| Port | Protocol | Description                                            |
| ---- | -------- | ------------------------------------------------------ |
| 8080 | HTTP     | Webserver export (optional, only if enabled in config) |

## Volumes

| Path      | Description                                          |
| --------- | ---------------------------------------------------- |
| `/config` | Configuration directory (must contain `config.yaml`) |
| `/logs`   | Application logs directory                           |

## Testing

To test the container with a single run (useful for troubleshooting):

```bash
docker run --rm \
  -v /path/to/config.yaml:/config/config.yaml \
  -v /path/to/logs:/logs \
  ghcr.io/anthony-spruyt/sungather:v0.5.3 \
  python3 /opt/sungather/sungather.py \
  -c /config/config.yaml \
  -l /logs/ \
  --runonce
```

## n8n Release Watcher

The `n8n-release-watcher.json` workflow automatically detects new SunGather releases and triggers a container build.

### What it does

1. Checks GitHub daily (midnight UTC) for new tags on `anthony-spruyt/SunGather`
2. Compares with the last processed version (stored in workflow static data)
3. If a new version is found:
   - Triggers the container build workflow with the exact upstream tag
   - Sends an email notification
   - Updates the stored version

**Note:** The workflow preserves the exact upstream tag format (including 'v' prefix if present) to ensure correct git checkout.

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

### Testing the Workflow

1. Open the workflow in n8n
2. Click **Execute Workflow** to run manually
3. Check the output of each node:
   - **Get GitHub Tags:** Should return tag list from GitHub
   - **Check New Version:** Shows `isNew: true` on first run
   - **Trigger Build Workflow:** Should return HTTP 204 (success)
   - **Send Notification:** Sends email to configured recipient

On subsequent runs, `isNew` will be `false` until a new release is published upstream.

## Related

- [Upstream Repository](https://github.com/anthony-spruyt/SunGather)
- [Upstream Documentation](https://github.com/anthony-spruyt/SunGather#readme)
