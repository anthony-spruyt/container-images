# Analysis Patterns by Dependency Type

Detailed patterns for detecting breaking changes in different dependency types found in this container-images repository.

## Upstream Source Updates

### Where Upstream Sources Live

Upstream sources are tracked in `<image>/metadata.yaml` with a `# renovate:` annotation pointing to a GitHub datasource.

```yaml
upstream: owner/repo
# renovate: datasource=github-tags depName=owner/repo
version: "1.0.0"
```

### Breaking Change Signals

| Signal                  | Severity | How to Detect                                              |
| ----------------------- | -------- | ---------------------------------------------------------- |
| Major version bump      | High     | Semver major: 1.x → 2.x                                    |
| CLI interface change    | High     | Changelog mentions removed/renamed commands or flags       |
| Config format change    | Medium   | Release notes mention config file format changes           |
| API breaking change     | Medium   | Changelog mentions removed/renamed API endpoints or fields |
| Build dependency change | Medium   | Upstream now requires different build tools or base images |
| Output format change    | Low      | Release notes mention changed output format                |

### Known Upstream Sources

**firemerge** (`anthony-spruyt/firemerge`): Transaction entry tool for Firefly III. Check for CLI flag changes, config format changes, and dependency updates that may affect the Dockerfile.

### Impact Assessment for Upstream Sources

1. Read `<image>/Dockerfile` — check if build references specific upstream paths, versions, or features
2. Read `<image>/test.sh` — check if tests rely on specific CLI behavior or output
3. If the upstream is just pulled as a binary and our Dockerfile/tests don't depend on changed features → **NO_IMPACT**
4. If CLI flags we use in test.sh were removed → **HIGH_IMPACT**

## Docker Base Image Updates

### Where Base Images Live

MegaLinter flavor base images are in `<flavor>/flavor.yaml`:

```yaml
# renovate: datasource=docker depName=oxsecurity/megalinter-ci_light
upstream_image: "oxsecurity/megalinter-ci_light:v9.3.0@sha256:..."
```

### Breaking Change Signals

| Signal                                    | Severity | How to Detect                                                    |
| ----------------------------------------- | -------- | ---------------------------------------------------------------- |
| Linter removed from base                  | High     | MegaLinter release notes mention removed linter                  |
| Linter renamed                            | High     | Linter key changed (e.g., `JAVASCRIPT_ES` → `JAVASCRIPT_ESLINT`) |
| Major version bump                        | High     | Semver major: v8 → v9                                            |
| Config format change                      | Medium   | MegaLinter config schema changed                                 |
| Linter version bump with breaking changes | Medium   | Linter's own changelog has breaking changes                      |
| New linter added to base                  | Low      | Usually informational only                                       |
| Base OS change                            | Low      | Alpine → Debian or version bumps                                 |

### Common MegaLinter Patterns

**oxsecurity/megalinter-ci_light:** The base for all flavors. Major version bumps (v8 → v9) may:

- Remove or rename linter keys
- Change Dockerfile structure
- Update supported descriptor format
- Change environment variable names

### Impact Assessment for Base Images

1. Read `<flavor>/flavor.yaml` — get list of `custom_linters` we use
2. Check if ALL linters in `custom_linters` are still supported in the new version
3. Check `megalinter-factory/generate.py` and `megalinter-factory/templates/` — verify template compatibility
4. If all our custom_linters exist in the new version → **NO_IMPACT**
5. If a linter we use was removed or renamed → **HIGH_IMPACT**

### Upstream Repo Discovery for Docker Images

Common mappings:

- `oxsecurity/megalinter-ci_light` → `oxsecurity/megalinter` (GitHub releases)
- `oxsecurity/megalinter` → `oxsecurity/megalinter` (same repo)

## GitHub Actions Updates

### Where Actions Live

GitHub Actions are in `.github/workflows/*.yaml`:

```yaml
uses: actions/checkout@v4
uses: docker/build-push-action@v6
uses: actions/attest-build-provenance@v2
```

### Breaking Change Signals

| Signal                     | Severity | How to Detect                                       |
| -------------------------- | -------- | --------------------------------------------------- |
| Input removed/renamed      | High     | Action changelog mentions removed inputs            |
| Output removed/renamed     | High     | Action changelog mentions removed outputs           |
| Major version bump         | High     | v3 → v4, v5 → v6                                    |
| Runner requirements change | Medium   | Action requires newer runner OS                     |
| Default behavior change    | Medium   | Changed defaults for inputs we don't set explicitly |
| Node.js version bump       | Low      | Action internals updated (usually transparent)      |

### Common Actions in This Repo

**actions/checkout:** Usually safe. Major bumps may change default behavior (e.g., fetch-depth).

**docker/build-push-action:** Check for changes to inputs like `push`, `tags`, `context`, `file`, `platforms`, `provenance`, `sbom`.

**actions/attest-build-provenance:** SLSA provenance attestation. Check for attestation format changes.

### Impact Assessment for Actions

1. Read `.github/workflows/` files that use the updated action
2. List all `with:` inputs we pass to the action
3. Cross-reference each input against the action's changelog
4. If we only use stable, unchanged inputs → **NO_IMPACT**
5. If an input we use was removed/renamed → **HIGH_IMPACT**

## Script and Tool Dependency Updates

### Where Script Deps Live

Tool versions are tracked in:

- `.devcontainer/initialize.sh` — tools installed in dev container
- `.devcontainer/devcontainer.json` — devcontainer features and settings
- Shell scripts at repo root (e.g., `lint.sh`)

### Breaking Change Signals

| Signal                    | Severity | How to Detect                         |
| ------------------------- | -------- | ------------------------------------- |
| CLI flag removed/renamed  | High     | Changelog mentions removed flags      |
| Config file format change | Medium   | Tool requires different config format |
| Output format change      | Medium   | May break scripts parsing output      |
| Minimum runtime version   | Low      | Tool requires newer Go/Node/Python    |

### Common Script Dependencies

**cilium-cli:** Used for Cilium management. Check for subcommand changes.

**talos (siderolabs/talos):** Talos Linux tooling. Check for `talosctl` CLI changes.

**renovate:** The Renovate bot itself. Check for config schema changes (usually backward-compatible).

### Impact Assessment for Script Deps

1. Read the scripts that use the tool (`.devcontainer/initialize.sh`, etc.)
2. Check which CLI flags and subcommands we use
3. If the tool is just installed and we use stable subcommands → **NO_IMPACT**
4. If flags we use were removed → **HIGH_IMPACT**

## Pre-commit Hook Updates

### Where Pre-commit Config Lives

Pre-commit hooks are in `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: "https://github.com/adrienverge/yamllint"
    rev: "v1.38.0"
    hooks:
      - id: "yamllint"
        args: ["--config-file", ".yamllint.yml"]
```

### Breaking Change Signals

| Signal                  | Severity | How to Detect                              |
| ----------------------- | -------- | ------------------------------------------ |
| Hook ID renamed         | High     | Hook no longer exists under old name       |
| Config format change    | Medium   | Hook requires different config file format |
| New default rules       | Low      | May flag new issues but builds still pass  |
| Python/Node version req | Low      | Hook requires newer runtime                |

### Common Pre-commit Hooks

**yamllint:** YAML linter. Config in `.yamllint.yml`. Usually safe.

**gitleaks:** Secret scanning. Config in `.gitleaks.toml`. Check for config schema changes.

**prettier:** Code formatter. Config in `.prettierrc.yaml`. Check for formatting rule changes.

**pre-commit-hooks (pre-commit/pre-commit-hooks):** Standard hooks. Very stable.

### Impact Assessment for Pre-commit Hooks

1. Read `.pre-commit-config.yaml` — check which hooks and args we use
2. Read the hook's config file (e.g., `.yamllint.yml`, `.gitleaks.toml`)
3. Pre-commit hook updates are almost always safe for patch/minor bumps
4. Major bumps → check if config format or hook IDs changed

## Changelog Parsing Heuristics

### Red Flag Keywords (case-insensitive)

**Critical (likely breaking):**

- "BREAKING CHANGE", "breaking:", "⚠️ breaking"
- "removed", "deletion", "no longer supported"
- "migration required", "action required", "manual steps"
- "incompatible", "not backward compatible"

**Warning (possibly breaking):**

- "deprecated", "will be removed"
- "changed default", "new default"
- "renamed", "moved"
- "requires", "prerequisite"
- "schema change", "API change", "config change"

**Informational (usually safe):**

- "added", "new feature", "enhancement"
- "fixed", "bug fix", "patch"
- "improved", "optimized", "performance"
- "documentation", "docs"

### Scoring Heuristic

When multiple signals are present:

- 1+ critical keywords → RISKY
- 3+ warning keywords → RISKY
- 1-2 warning keywords + patch version → SAFE (likely just mentions of future deprecations)
- 1-2 warning keywords + minor/major version → RISKY
- Only informational keywords → SAFE
- No changelog found → UNKNOWN

## GitHub Release Notes Patterns

### Common Formats

**Conventional Commits style:**

```
## Breaking Changes
- feat!: removed X
## Features
- feat: added Y
## Bug Fixes
- fix: resolved Z
```

**Keep a Changelog style:**

```
## [1.2.0] - 2026-01-15
### Added
### Changed
### Deprecated
### Removed    ← CHECK THIS SECTION
### Fixed
### Security
```

**GitHub auto-generated:**

```
## What's Changed
* feat: add X by @user in #123
* fix: resolve Y by @user in #124
**Full Changelog**: https://github.com/org/repo/compare/v1.0.0...v1.1.0
```

### What to Extract

1. **Removed/Breaking section** → verbatim quote
2. **Upgrading/Migration section** → verbatim quote
3. **Changed section** → summarize behavior changes
4. **Bug fixes** → note if they fix issues affecting our builds

## Impact Assessment Against Our Config

**The most important analysis step.** A breaking change only matters if it affects what we actually use.

### Where Our Config Lives

```text
<image-name>/
├── metadata.yaml          # Version and upstream source
├── flavor.yaml            # MegaLinter flavor config (megalinter-* images only)
├── Dockerfile             # Build instructions (may not exist for flavors)
├── test.sh                # CI tests run after build
├── .trivyignore           # Per-image vulnerability ignores
└── assets/                # Additional build assets

.github/workflows/         # CI/CD pipelines
.devcontainer/             # Dev environment setup
.pre-commit-config.yaml    # Pre-commit hook versions
megalinter-factory/        # MegaLinter flavor generator
```

### Common NO_IMPACT Scenarios

These breaking changes rarely affect this repository:

| Breaking Change            | Why Usually NO_IMPACT                               |
| -------------------------- | --------------------------------------------------- |
| Kubernetes API changes     | This repo builds images, doesn't deploy to clusters |
| Helm chart value changes   | No Helm charts in this repo                         |
| ARM64-only changes         | CI builds for linux/amd64                           |
| Cloud provider integration | No cloud provider dependencies                      |
| Database migration changes | No databases in build pipeline                      |
| Runtime config changes     | Images are built, not run in CI (except tests)      |

### Common HIGH_IMPACT Scenarios

These breaking changes frequently affect this repository:

| Breaking Change                       | Why Usually HIGH_IMPACT                            |
| ------------------------------------- | -------------------------------------------------- |
| MegaLinter linter key renamed/removed | Flavors reference specific linter keys             |
| Dockerfile syntax changes             | Build pipeline depends on Dockerfile compatibility |
| GitHub Actions input/output changes   | CI workflows use specific action inputs            |
| Container registry API changes        | Build pushes to ghcr.io                            |
| Pre-commit hook ID changes            | Pre-commit runs in CI                              |
| Build tool CLI changes                | Scripts use specific CLI flags                     |
