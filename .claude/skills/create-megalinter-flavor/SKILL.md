---
name: create-megalinter-flavor
description: Create a new MegaLinter flavor image configuration from language definitions
allowed-tools:
  - Read
  - Write
  - Bash
  - AskUserQuestion
argument-hint: <languages> (e.g. go-python)
---

# Create MegaLinter Flavor

You are creating a new MegaLinter flavor image configuration. Follow these steps precisely.

Flavors are named by the languages they lint and shared by every repo with that mix. Each language's linters and toolchain live once in `megalinter-factory/languages/<language>.yaml`; a flavor lists languages, it does not copy their linters. Only create a flavor a repo actually needs.

## Input Parsing

Parse the arguments provided: `$ARGUMENTS`

- **name**: The first argument (required) - the languages joined by `-`, e.g. `go-python`

## Step 1: Validate Name

The name must:

1. Match pattern `^[a-z][a-z0-9-]*$` (lowercase, alphanumeric, hyphens, starts with letter)
2. Not conflict with existing directory `megalinter-<name>/`

Check for existing directory:

```bash
ls -d megalinter-<name>/ 2>/dev/null
```

If validation fails, inform the user and stop.

## Step 2: Get Available Linters

Run the extractor to get available linters from MegaLinter:

```bash
python megalinter-factory/megalinter_extractor.py 2>&1 | head -100
```

This extracts linter information directly from MegaLinter's descriptors.

## Step 3: Resolve Languages

Split the name on `-` into languages (a language file name may itself contain `-`; match the longest names in `megalinter-factory/languages/` first). For each one:

- If `megalinter-factory/languages/<language>.yaml` exists, use it as is.
- Otherwise create it: `linters` lists the MegaLinter keys (validate each against the extractor output), plus `extra_dockerfile`, `extra_test_linters` and `extra_test_env_vars` when the language needs a toolchain or settings the upstream base lacks. Fragments reference the file's own fields as `{{ language.<field> }}`. Put a `# renovate:` annotation on every pinned version. See `languages/go.yaml` for a toolchain example. Never name a file after a tool: a language file is that language's one linter set.

`megalinter-factory/base.yaml` already gives every flavor ACTION_ACTIONLINT, MARKDOWN_MARKDOWNLINT and SPELL_LYCHEE; do not repeat them.

**Important**: Some linters are already included in the `ci_light` base flavor. The extractor output shows `ci_light has N linters` - these DON'T need to be in a language's `linters`. The exception is a language that consists of such a linter, like `docker` (DOCKERFILE_HADOLINT). Listing it means `test.sh` checks the linter and the removal guard protects it, at the cost of one redundant binary copy.

Linters already in `ci_light` as of MegaLinter v10.1.0 (23 total) — the extractor output is authoritative if it disagrees:

- BASH_SHELLCHECK, BASH_SHFMT
- DOCKERFILE_HADOLINT
- JSON_JSONLINT, JSON_PRETTIER, JSON_V8R
- YAML_YAMLLINT, YAML_PRETTIER, YAML_V8R
- REPOSITORY_BETTERLEAKS, REPOSITORY_SECRETLINT, REPOSITORY_TRIVY, REPOSITORY_TRIVY_SBOM
- REPOSITORY_GRYPE, REPOSITORY_SYFT, REPOSITORY_TRUFFLEHOG, REPOSITORY_LS_LINT, REPOSITORY_GIT_DIFF
- REPOSITORY_OSV_SCANNER
- COPYPASTE_JSCPD, XML_XMLLINT, ENV_DOTENV_LINTER, GROOVY_NPM_GROOVY_LINT

**Built-in linters requiring specific base flavors:**

Some linters are built-in (no install needed) but require tools only available in specific base flavors:

| Linter                  | Required Base Flavor              |
| ----------------------- | --------------------------------- |
| TERRAFORM_TERRAFORM_FMT | `terraform`                       |
| CSHARP_DOTNET_FORMAT    | `dotnet` or `dotnetweb`           |
| VBDOTNET_DOTNET_FORMAT  | `dotnet` or `dotnetweb`           |
| SWIFT_SWIFTLINT         | `swift`                           |
| JAVA\_\* linters        | `java`                            |
| RUST_CLIPPY             | `rust`                            |

Prefer bringing the toolchain in through the language's `extra_dockerfile` (as `go.yaml` does) so the flavor can stay on `ci_light`. If that is not practical, warn the user they need to change `upstream_image` to the matching upstream flavor.

## Step 4: Auto-Select Base Flavor

The generator will automatically use `ci_light` as the base flavor (it's the lightest). The user can override this by editing `upstream_image` after creation.

## Step 5: Generate Configuration Files

Create the directory and both required configuration files.

### 5a: Create flavor.yaml

Create `megalinter-<name>/flavor.yaml`:

```yaml
---
name: <name>
description: "MegaLinter for <languages> repositories"

# renovate: datasource=docker depName=ghcr.io/oxsecurity/megalinter-ci_light
upstream_image: "ghcr.io/oxsecurity/megalinter-ci_light:<version>@sha256:<digest>"

languages:
  - <language-1>
  - <language-2>
```

Copy `<version>` and `<digest>` from an existing ci_light flavor's `flavor.yaml` so all flavors share one base that Renovate keeps current.

### 5b: Register with release-please

Versions are owned by release-please. See [docs/releases.md](../../../docs/releases.md).

1. Add `megalinter-<name>` to `packages` in `release-please-config.json`, copying `megalinter-python`'s entry. New flavors have no `v` prefix (`"include-v-in-tag": false`) and start at `"initial-version": "1.0.0"`.
2. Add `"megalinter-<name>": "0.0.0"` to `.release-please-manifest.json`. A non-zero entry with no matching tag counts as already released, so the first `feat` would ship 1.1.0.
3. Add outputs and a build job to `.github/workflows/release-please.yaml`, copying an existing flavor without a `v` prefix. Omit `tag-prefix: "v"` — it must match `include-v-in-tag`.
4. Add the flavor to `EXPECTED_LINTERS` in `megalinter-factory/test_compose.py`.
5. Release it with a `feat(megalinter):` commit. Renovate's `sourceDirectory` rule for flavors lives in repo-operator's `.github/renovate/package-rules.json5`; ask for one there.

## Step 6: Run Factory Generator

Run the factory generator to verify the configuration produces valid output:

```bash
python megalinter-factory/generate.py megalinter-<name>/
```

Review the generated `Dockerfile` and `test.sh` to verify they look correct. Generated files are gitignored — CI regenerates them at build time.

## Step 7: Report Success

Inform the user:

1. Configuration files created:
   - `megalinter-<name>/flavor.yaml` - flavor configuration
   - any new `megalinter-factory/languages/<language>.yaml`
2. Registered with release-please and Renovate; the daily Trivy scan finds the image on GHCR by itself
3. Linter versions will be extracted from MegaLinter at build time
4. Next steps:
   - Commit the changes
   - CI will automatically generate Dockerfile and build the image
   - Or run locally: `python megalinter-factory/generate.py megalinter-<name>/`

## Validation Rules Summary

| Check           | Validation                                                  |
| --------------- | ----------------------------------------------------------- |
| Name format     | `^[a-z][a-z0-9-]*$`                                         |
| Name uniqueness | No existing `megalinter-<name>/` directory                  |
| Languages       | Each has `megalinter-factory/languages/<language>.yaml`     |
| Linter keys     | Must exist in MegaLinter descriptors                        |

## Example Output

For `/create-megalinter-flavor go-python`, both languages already exist, so only the flavor is written:

```yaml
---
name: go-python
description: "MegaLinter for Go and Python repositories"

# renovate: datasource=docker depName=ghcr.io/oxsecurity/megalinter-ci_light
upstream_image: "ghcr.io/oxsecurity/megalinter-ci_light:<version>@sha256:<digest>"

languages:
  - go
  - python
```
