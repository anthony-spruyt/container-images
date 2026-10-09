# Container Images

[![License](https://img.shields.io/github/license/anthony-spruyt/container-images)](https://github.com/anthony-spruyt/container-images/blob/main/LICENSE) [![CI](https://github.com/anthony-spruyt/container-images/actions/workflows/ci.yaml/badge.svg?branch=main)](https://github.com/anthony-spruyt/container-images/actions/workflows/ci.yaml)
[![Trivy Scan](https://github.com/anthony-spruyt/container-images/actions/workflows/trivy-scan.yaml/badge.svg?branch=main)](https://github.com/anthony-spruyt/container-images/actions/workflows/trivy-scan.yaml)

Container images I use, published to `ghcr.io/anthony-spruyt/<image>` and `docker.io/aspruyt/<image>`. Some wrap upstream software, some are my own Dockerfiles. The daily Trivy scan checks the published images, and each release attaches a build provenance attestation.

## Development

See [DEVELOPMENT.md](DEVELOPMENT.md) for development environment setup.

## Usage

Pull an image:

```bash
docker pull ghcr.io/anthony-spruyt/chrony:latest
```

## Adding a New Image

Versions are owned by release-please. See [docs/releases.md](docs/releases.md).

1. Create a directory named after the image, containing a `Dockerfile`.

2. Register the image in `release-please-config.json` and `.release-please-manifest.json`.

3. Add a `metadata.yaml` with the image's build settings. If the image has a `test.sh`, set `test-command` to run it; CI doesn't find it automatically:

   ```yaml
   free-disk: true
   test-command: bash ./chrony/test.sh "$IMAGE_REF"
   ```

   The fields are documented in repo-operator's [docs/ci.md](https://github.com/anthony-spruyt/repo-operator/blob/main/docs/ci.md#detect-images).

4. Ask for the image to be added to `retentionPackages` in repo-operator's `src/repos.yaml`, which writes the synced `container-retention.yaml`.

5. Add a `sourceDirectory` rule to `renovate-overrides.json5` so Renovate shows its release notes.

CI and releases find images in `release-please-config.json`, so no workflow changes are needed. Merging a conventional commit that touches the directory then opens a release PR; merging that cuts the tag and publishes the image.

### Variant of an Existing Image

To share another image's sources but use your own `Dockerfile`, add a `metadata.yaml` setting `build_context`:

```yaml
build_context: llm-guard
```

## Adding a Custom MegaLinter Flavor

Custom MegaLinter flavors extend official flavors with additional linters. They are named by the languages they lint (`megalinter-go`, `megalinter-go-python`). Each language's linters and toolchain are defined once in `megalinter-factory/languages/<language>.yaml`, and a flavor lists the languages it combines.

### Using Claude Code

The `/create-megalinter-flavor` command takes the languages, joined by `-`, and writes the `flavor.yaml` for you:

```bash
/create-megalinter-flavor go-python
```

The command will:

1. Validate the flavor name and check for conflicts
2. Reuse each language's definition in `megalinter-factory/languages/`, creating any that are missing
3. Generate `megalinter-<name>/flavor.yaml` with Renovate annotations
4. Register the flavor with release-please and `EXPECTED_LINTERS`

### Manual Setup

1. Create a directory for your flavor:

   ```bash
   mkdir megalinter-<name>/
   ```

2. Create `flavor.yaml` listing its languages:

   ```yaml
   name: go-python
   description: "MegaLinter for Go and Python repositories"

   # renovate: datasource=docker depName=ghcr.io/oxsecurity/megalinter-ci_light
   upstream_image: "ghcr.io/oxsecurity/megalinter-ci_light:v10.1.0@sha256:..."

   languages:
     - go
     - python
   ```

   Linters needed by one flavor only can go in its `custom_linters`. Anything a second flavor would need belongs in a language definition.

3. Copy an existing flavor's `metadata.yaml` and replace the flavor name in `prepare-command` and `test-command`.

4. Register the flavor with release-please:
   - Add `megalinter-<name>` to `packages` in `release-please-config.json`, copying `megalinter-python`'s entry.
   - Add `"megalinter-<name>": "0.0.0"` to `.release-please-manifest.json`.

   CI and the release workflows only build release-please packages, so an unregistered flavor never builds.

5. Add the flavor to `EXPECTED_LINTERS` in `megalinter-factory/test_compose.py`.

6. Ask for the flavor to be added to `retentionPackages` in repo-operator's `src/repos.yaml`, which writes the synced `container-retention.yaml`.

7. Ask for a `sourceDirectory` rule for the flavor in repo-operator's `.github/renovate/package-rules.json5`, which every repo extends, so Renovate shows its release notes.

8. Commit the files. CI generates the Dockerfile and test.sh, then builds the flavor.

### Available Linters

Linter info comes from MegaLinter's descriptors at build time: <https://github.com/oxsecurity/megalinter/tree/main/megalinter/descriptors>.

### Version Updates

Linter versions come from MegaLinter at build time. The weekly rebuild picks up new ones.

For the base image, Renovate tracks the upstream MegaLinter version:

```yaml
# renovate: datasource=docker depName=ghcr.io/oxsecurity/megalinter-ci_light
upstream_image: "ghcr.io/oxsecurity/megalinter-ci_light:v10.1.0@sha256:..."
```

When Renovate creates a PR updating `flavor.yaml`, CI regenerates the Dockerfile and builds. Toolchain pins in `megalinter-factory/languages/` are tracked the same way; once such a change merges, `Rebuild MegaLinter Flavors` opens a PR stamping just the flavors that use that language, which releases them.

### Local Development

To test locally, generate files first:

```bash
pip install pyyaml jinja2
python megalinter-factory/generate.py megalinter-<name>/
```

Generated files (`Dockerfile`, `test.sh`) are regenerated by CI at build time.

## Build Triggers

CI builds but never pushes. Every publish goes through release-please — see [docs/releases.md](docs/releases.md).

A pull request or push to `main` builds and tests every image with a changed file in its directory, one of its `watch` paths, or its `build_context`. Changelogs and `.release-please-manifest.json` never trigger a build. Changes to `megalinter-factory/` build all flavors but release none: the factory is not a release-please package. Publishing happens when the resulting release PR merges. See
repo-operator's [docs/ci.md](https://github.com/anthony-spruyt/repo-operator/blob/main/docs/ci.md#images) for the details.

To republish a release whose build failed after tagging, run `Rebuild Release` from the release tag (see [docs/releases.md](docs/releases.md#rebuild-release)):

```bash
gh workflow run rebuild-release.yaml --ref <tag> -f image=<image> -f version=<version>
```

## Automatic Version Updates

Renovate updates dependencies *inside* an image (base images, packages). The resulting commit lands on main and release-please cuts a patch release for that image.

Image versions themselves are never set by Renovate; they live in `.release-please-manifest.json`.

## Security

See [SECURITY.md](SECURITY.md) for security policy and controls.
