# Container Images

[![Lint](https://github.com/anthony-spruyt/container-images/actions/workflows/lint.yaml/badge.svg)](https://github.com/anthony-spruyt/container-images/actions/workflows/lint.yaml)
[![Build and Push](https://github.com/anthony-spruyt/container-images/actions/workflows/build-and-push.yaml/badge.svg)](https://github.com/anthony-spruyt/container-images/actions/workflows/build-and-push.yaml)

Monorepo for custom-built container images published to GitHub Container Registry.

## Development Environment

This repository uses a VS Code devcontainer for a consistent development experience.

### Prerequisites

- [VS Code](https://code.visualstudio.com/) with the [Dev Containers extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers)
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) or Docker Engine
- SSH agent running with your keys loaded (for git operations)
- GitHub token in `~/.secrets/.env` (for GitHub CLI operations)

### SSH Agent Setup

The devcontainer uses SSH agent forwarding for secure git authentication. Your private keys stay on the host.

The devcontainer also mounts your `~/.gitconfig` (read-only) for git identity and commit signing. To enable SSH commit signing on your host:

```bash
git config --global gpg.format ssh
git config --global user.signingkey "$(cat ~/.ssh/id_ed25519.pub)"
git config --global commit.gpgsign true
```

**Linux/WSL:**

```bash
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_ed25519  # or your key path
```

For passphrase-protected keys, use `keychain` to persist across sessions:

```bash
# Install: sudo apt install keychain
# Add to ~/.bashrc or ~/.zshrc:
eval "$(keychain --eval --agents ssh id_ed25519)"
```

`keychain` prompts for your passphrase once per reboot and reuses the agent across terminals.

**macOS:**

```bash
ssh-add --apple-use-keychain ~/.ssh/id_ed25519
```

Keys added with `--apple-use-keychain` persist across restarts.

**Windows (Git Bash):**

```bash
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_ed25519
```

Or enable the OpenSSH Authentication Agent service in Windows Services.

### GitHub CLI Setup

The devcontainer loads environment variables from `~/.secrets/.env` on your host. Create this file with a GitHub token for CLI operations:

```bash
mkdir -p ~/.secrets
chmod 700 ~/.secrets
echo "GH_TOKEN=ghp_your_token_here" > ~/.secrets/.env
chmod 600 ~/.secrets/.env
```

Create a token at [GitHub Settings > Developer settings > Personal access tokens](https://github.com/settings/tokens) with `repo` and `workflow` scopes.

### Opening the Devcontainer

1. Clone the repository
2. Open the folder in VS Code
3. When prompted, click "Reopen in Container" (or run `Dev Containers: Reopen in Container` from the command palette)

### Included Tools

- **Docker-in-Docker** - Build and test container images
- **Pre-commit hooks** - Automatic linting on commit (gitleaks, prettier, yamllint)
- **MegaLinter** - Run `./lint.sh` for comprehensive linting
- **GitHub CLI** - `gh` command for GitHub operations
- **Safe-chain** - Supply chain attack protection for npm/pip

### Verify Setup

After opening the devcontainer, verify everything is working:

```bash
./verify-setup.sh
```

This checks Docker-in-Docker, pre-commit hooks, safe-chain protection, GitHub CLI, and SSH agent forwarding.

## Available Images

| Image     | Upstream                                          | Registry                           |
| --------- | ------------------------------------------------- | ---------------------------------- |
| firemerge | [lvu/firemerge](https://github.com/lvu/firemerge) | `ghcr.io/anthony-spruyt/firemerge` |

## Usage

Pull an image:

```bash
docker pull ghcr.io/anthony-spruyt/firemerge:latest
```

## Adding a New Image

1. Create a directory with the image name
2. Add `metadata.yaml`:

   ```yaml
   upstream: owner/repo
   version: "1.0.0"
   ```

3. Optionally add a custom `Dockerfile` to override the upstream's
4. Update `.github/workflows/build-and-push.yaml`:
   - Add upstream to `ALLOWED_UPSTREAMS` env var
   - Add image name to `inputs.image.options` list
5. Update `.github/dependabot.yml` to track Docker base images:

   ```yaml
   - package-ecosystem: "docker"
     directory: "/<image-name>"
     schedule:
       interval: weekly
   ```

6. Push to main - the image will be built and published automatically

## Build Triggers

### Automatic

Pushing changes to `metadata.yaml` or `Dockerfile` on main triggers a build using the version in metadata.

### Manual / n8n Integration

Trigger via GitHub API (workflow_dispatch):

```bash
# Dry run (default) - builds and scans but doesn't push or release
curl -X POST \
  -H "Authorization: token $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github.v3+json" \
  https://api.github.com/repos/anthony-spruyt/container-images/actions/workflows/build-and-push.yaml/dispatches \
  -d '{"ref":"main","inputs":{"image":"firemerge","version":"0.5.3"}}'

# Production build - pushes to GHCR and creates release
curl -X POST \
  -H "Authorization: token $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github.v3+json" \
  https://api.github.com/repos/anthony-spruyt/container-images/actions/workflows/build-and-push.yaml/dispatches \
  -d '{"ref":"main","inputs":{"image":"firemerge","version":"0.5.3","dry_run":"false"}}'
```

Parameters:

- **image** (required): Image name from allowed list (e.g., `firemerge`)
- **version** (optional): Semver tag to build (e.g., `0.5.3`) - checks out this tag from upstream
- **dry_run** (optional, default: `true`): When `true`, builds and scans the image but skips push to GHCR and release creation. Set to `false` for production builds.

## n8n Workflow

Create an n8n workflow to automatically trigger builds when upstream repos release new versions.

### Workflow Design

```text
┌─────────────┐     ┌──────────────────┐     ┌─────────────────────┐
│  Schedule   │────▶│  GitHub API:     │────▶│  GitHub API:        │
│  (daily)    │     │  Get latest tag  │     │  Trigger workflow   │
└─────────────┘     └──────────────────┘     └─────────────────────┘
                            │
                            ▼
                    ┌──────────────────┐
                    │  Compare with    │
                    │  last known ver  │
                    └──────────────────┘
```

### Nodes

1. **Schedule Trigger** - Run daily (or use GitHub webhook for instant updates)

2. **Get Latest Release** - HTTP Request to GitHub API:

   ```text
   GET https://api.github.com/repos/lvu/firemerge/releases/latest
   ```

   Or for tags:

   ```text
   GET https://api.github.com/repos/lvu/firemerge/tags?per_page=1
   ```

3. **Compare Version** - Check if version differs from last triggered build (store in n8n static data or external DB)

4. **Trigger Build** - HTTP Request (only if new version):

   ```text
   POST https://api.github.com/repos/anthony-spruyt/container-images/actions/workflows/build-and-push.yaml/dispatches

   Headers:
     Authorization: Bearer $GITHUB_PAT
     Accept: application/vnd.github.v3+json

   Body:
     {
       "ref": "main",
       "inputs": {
         "image": "firemerge",
         "version": "{{ $json.name }}",
         "dry_run": "false"
       }
     }
   ```

   Note: Set `dry_run` to `"false"` for production builds. Default is `"true"` (dry run mode).

### Required Secrets

- **GitHub PAT** with `repo` and `workflow` scopes for triggering workflow_dispatch

## Security

See [SECURITY.md](SECURITY.md) for security policy and controls.

After creating the repository, apply the GitHub rulesets:

```bash
./.github/apply-rulesets.sh
```
