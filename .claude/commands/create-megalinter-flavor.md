---
description: Create a new MegaLinter flavor image configuration
allowed-tools:
  - Read
  - Write
  - Glob
  - Bash
  - AskUserQuestion
argument-hint: <name> [LINTER1,LINTER2,...]
---

# Create MegaLinter Flavor

You are creating a new MegaLinter flavor image configuration. Follow these steps precisely.

## Input Parsing

Parse the arguments provided: `$ARGUMENTS`

- **name**: The first argument (required) - the flavor name
- **linters**: Optional comma-separated list of linter keys (e.g., `ACTION_ACTIONLINT,MARKDOWN_MARKDOWNLINT`)

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

## Step 3: Get Linter Selection

If linters were provided as arguments, validate each one exists in MegaLinter (check extractor output).

**Important**: Some linters are already included in the `ci_light` base flavor. The extractor output shows `ci_light has N linters` - these DON'T need to be in `custom_linters`. Only add linters that aren't in the base flavor.

Linters already in `ci_light` (24 total):

- BASH_SHELLCHECK, BASH_SHFMT
- DOCKERFILE_HADOLINT
- JSON_JSONLINT, JSON_PRETTIER, JSON_V8R, JSON_ESLINT_PLUGIN_JSONC
- YAML_YAMLLINT, YAML_PRETTIER, YAML_V8R
- REPOSITORY_GITLEAKS, REPOSITORY_SECRETLINT, REPOSITORY_TRIVY, REPOSITORY_TRIVY_SBOM
- REPOSITORY_GRYPE, REPOSITORY_SYFT, REPOSITORY_TRUFFLEHOG, REPOSITORY_LS_LINT, REPOSITORY_GIT_DIFF
- COPYPASTE_JSCPD, MAKEFILE_CHECKMAKE, XML_XMLLINT, ENV_DOTENV_LINTER, GROOVY_NPM_GROOVY_LINT

**NOT in `ci_light`** (must be added as custom_linters):

- ACTION_ACTIONLINT
- MARKDOWN_MARKDOWNLINT, SPELL_LYCHEE
- PYTHON_PYLINT, PYTHON_RUFF
- (and most language-specific linters)

**Built-in linters requiring specific base flavors:**

Some linters are built-in (no install needed) but require tools only available in specific base flavors:

| Linter                  | Required Base Flavor              |
| ----------------------- | --------------------------------- |
| TERRAFORM_TERRAFORM_FMT | `terraform`                       |
| CSHARP_DOTNET_FORMAT    | `dotnet` or `dotnetweb`           |
| VBDOTNET_DOTNET_FORMAT  | `dotnet` or `dotnetweb`           |
| SWIFT_SWIFTLINT         | `swift`                           |
| GO\_\* linters          | `go`                              |
| JAVA\_\* linters        | `java`                            |
| PYTHON\_\* linters      | `python` (or `ci_light` for some) |
| RUST_CLIPPY             | `rust`                            |

If a user requests these linters with `ci_light` base, warn them they need to change `upstream_image` to the appropriate flavor (e.g., `oxsecurity/megalinter-terraform`).

If NO linters were provided, use AskUserQuestion to help the user select linters interactively. Present linters grouped by category:

- ACTION: GitHub Actions linters
- BASH: Shell script linters
- DOCKERFILE: Container linters
- JSON/YAML: Data format linters
- MARKDOWN: Documentation linters
- PYTHON: Python linters
- REPOSITORY: Security/scanning linters
- TERRAFORM: Infrastructure linters
- (etc.)

## Step 4: Auto-Select Base Flavor

The generator will automatically use `ci_light` as the base flavor (it's the lightest). The user can override this by editing `upstream_image` after creation.

## Step 5: Generate flavor.yaml

Create `megalinter-<name>/flavor.yaml` with this simple structure:

```yaml
# MegaLinter Flavor Factory Configuration
# Source of truth for megalinter-<name> flavor
#
# To regenerate Dockerfile and test.sh:
#   python megalinter-factory/generate.py megalinter-<name>/
#
# Linter versions are automatically extracted from MegaLinter at build time.
---
name: <name>
description: "<user-provided or auto-generated description>"

# Upstream MegaLinter base image (Renovate tracks this)
# renovate: datasource=docker depName=oxsecurity/megalinter-ci_light
upstream_image: "oxsecurity/megalinter-ci_light:v9.3.0@sha256:a71e62c83e3b2d52316e7322b9168e1588e9bcf454dbf9b21fc71b0954786e5e"

# Additional linters not in base flavor
# Just list linter keys - versions come from MegaLinter automatically
custom_linters:
  - <LINTER_KEY_1>
  - <LINTER_KEY_2>
```

**Note**: For the upstream_image digest, look it up with:

```bash
docker buildx imagetools inspect oxsecurity/megalinter-ci_light:v9.3.0 --format '{{json .Manifest}}' | jq -r '.digest'
```

## Step 6: Report Success

Inform the user:

1. The flavor.yaml has been created at `megalinter-<name>/flavor.yaml`
2. Linter versions will be extracted from MegaLinter at build time
3. Next steps:
   - Commit the changes
   - CI will automatically generate Dockerfile and build the image
   - Or run locally: `python megalinter-factory/generate.py megalinter-<name>/`

## Validation Rules Summary

| Check           | Validation                                 |
| --------------- | ------------------------------------------ |
| Name format     | `^[a-z][a-z0-9-]*$`                        |
| Name uniqueness | No existing `megalinter-<name>/` directory |
| Linter keys     | Must exist in MegaLinter descriptors       |

## Example Output

For `/create-megalinter-flavor test-ci ACTION_ACTIONLINT,MARKDOWN_MARKDOWNLINT`:

```yaml
name: test-ci
description: "Custom MegaLinter for CI testing"

# renovate: datasource=docker depName=oxsecurity/megalinter-ci_light
upstream_image: "oxsecurity/megalinter-ci_light:v9.3.0@sha256:a71e62c83e3b2d52316e7322b9168e1588e9bcf454dbf9b21fc71b0954786e5e"

custom_linters:
  - ACTION_ACTIONLINT
  - MARKDOWN_MARKDOWNLINT
```
