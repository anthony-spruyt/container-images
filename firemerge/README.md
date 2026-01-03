# Firemerge Container Image

Semi-automated transaction entry for Firefly III.

- **Upstream:** <https://github.com/lvu/firemerge>
- **Container:** `ghcr.io/anthony-spruyt/firemerge`

## n8n Release Watcher

The `n8n-release-watcher.json` workflow automatically detects new Firemerge releases and triggers a container build.

### What it does

1. Checks GitHub daily (midnight UTC) for new tags on `lvu/firemerge`
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

### Testing

1. Open the workflow in n8n
2. Click **Execute Workflow** to run manually
3. Check the output of each node:
   - **Get GitHub Tags:** Should return tag list from GitHub
   - **Check New Version:** Shows `isNew: true` on first run
   - **Trigger Build Workflow:** Should return HTTP 204 (success)
   - **Send Notification:** Sends email to configured recipient

On subsequent runs, `isNew` will be `false` until a new release is published upstream.
