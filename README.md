# Container Images

[![License](https://img.shields.io/github/license/anthony-spruyt/container-images)](https://github.com/anthony-spruyt/container-images/blob/main/LICENSE)
[![Lint](https://github.com/anthony-spruyt/container-images/actions/workflows/lint.yaml/badge.svg)](https://github.com/anthony-spruyt/container-images/actions/workflows/lint.yaml)
[![Build and Push](https://github.com/anthony-spruyt/container-images/actions/workflows/build-and-push.yaml/badge.svg)](https://github.com/anthony-spruyt/container-images/actions/workflows/build-and-push.yaml)
[![Trivy Scan](https://github.com/anthony-spruyt/container-images/actions/workflows/trivy-weekly-scan.yaml/badge.svg)](https://github.com/anthony-spruyt/container-images/actions/workflows/trivy-weekly-scan.yaml)
[![Stars](https://img.shields.io/github/stars/anthony-spruyt/container-images)](https://github.com/anthony-spruyt/container-images/stargazers)
[![Forks](https://img.shields.io/github/forks/anthony-spruyt/container-images)](https://github.com/anthony-spruyt/container-images/forks)
[![Contributors](https://img.shields.io/github/contributors/anthony-spruyt/container-images)](https://github.com/anthony-spruyt/container-images/graphs/contributors)
[![Issues](https://img.shields.io/github/issues/anthony-spruyt/container-images)](https://github.com/anthony-spruyt/container-images/issues)

Monorepo for custom-built container images published to GitHub Container Registry.

## Development

See [DEVELOPMENT.md](DEVELOPMENT.md) for development environment setup.

## Available Images

| Image     | Upstream                                                                | Registry                           |
| --------- | ----------------------------------------------------------------------- | ---------------------------------- |
| chrony    | Local (no upstream)                                                     | `ghcr.io/anthony-spruyt/chrony`    |
| firemerge | [anthony-spruyt/firemerge](https://github.com/anthony-spruyt/firemerge) | `ghcr.io/anthony-spruyt/firemerge` |

## Usage

Pull an image:

```bash
docker pull ghcr.io/anthony-spruyt/firemerge:latest
```

## Adding a New Image

### Option 1: Build from Upstream Source

Use this when building from an external repository (e.g., a GitHub project):

1. Create a directory with the image name
2. Add `metadata.yaml`:

   ```yaml
   upstream: owner/repo
   version: "1.0.0"
   ```

3. Optionally add a custom `Dockerfile` to override the upstream's
4. Update workflows:
   - Add upstream to `allowed-upstreams` in both `.github/workflows/build-and-push.yaml` and `.github/workflows/test-pr.yaml`
   - Add image name to `inputs.image.options` list in `build-and-push.yaml`
5. Add to `.github/dependabot.yml` to track base image updates:

   ```yaml
   - package-ecosystem: "docker"
     directory: "/<image-name>"
     schedule:
       interval: weekly
   ```

6. Push to main - the image will be built and published automatically

### Option 2: Build from Local Dockerfile

Use this for custom images with no upstream source:

1. Create a directory with the image name
2. Add your `Dockerfile` and any required files
3. Add `metadata.yaml` (upstream can be omitted):

   ```yaml
   version: "1.0.0"
   ```

4. Update `.github/workflows/build-and-push.yaml`:
   - Add image name to `inputs.image.options` list (no upstream allowlist needed)
5. Add to `.github/dependabot.yml` to track base image updates:

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
