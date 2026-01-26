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

## Step 2: Load Linter Catalog

Read the linter sources catalog:

- `megalinter-factory/linter-sources.yaml`

This file contains:

- `base_flavor_linters`: Linters pre-installed in each base MegaLinter flavor
- `custom_linters`: Installation details for all available linters

## Step 3: Get Linter Selection

If linters were provided as arguments, validate each one exists in `custom_linters`.

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

Analyze the selected linters against `base_flavor_linters` to find the optimal base:

1. For each base flavor, count how many requested linters are pre-installed
2. Select the flavor with highest coverage (fewest custom installs needed)
3. When tied, prefer smaller images (fewer total linters): ci_light < documentation < security < go < ruby < rust < swift < php < java < python < javascript < terraform < dotnet < dotnetweb < c_cpp < cupcake
4. Default to `ci_light` if no linters match any base

Report the selection rationale to the user.

## Step 5: Generate flavor.yaml

Create `megalinter-<name>/flavor.yaml` with this structure:

```yaml
# MegaLinter Flavor Factory Configuration
# Source of truth for megalinter-<name> flavor
#
# To regenerate Dockerfile, test.sh, and metadata.yaml:
#   python megalinter-factory/generate.py megalinter-<name>/
---
name: <name>
description: "<user-provided or auto-generated description>"

# Upstream MegaLinter base image (combined version+digest for atomic Renovate updates)
# renovate: datasource=docker depName=oxsecurity/megalinter-<base_flavor>
upstream_image: "oxsecurity/megalinter-<base_flavor>:v9.3.0@sha256:<digest>"

# Additional linters not in base flavor
custom_linters:
  # <linter description>
  - name: <lowercase-linter-name>
    linter_key: <LINTER_KEY>
    type: <type from linter-sources.yaml>
    # For docker_binary type, use combined image ref:
    # renovate: datasource=docker depName=<source_image>
    image: "<source_image>:<version>@sha256:<digest>"
    binary_path: <binary_path from linter-sources.yaml>
    target_path: <target_path from linter-sources.yaml>
    # For npm/pip/go/cargo types, use separate version field:
    # renovate: datasource=<npm|pypi|go|crate> depName=<package>
    version: "<default_version from linter-sources.yaml>"
    version_command: "<version_command from linter-sources.yaml>"
    description: "<description from linter-sources.yaml>"
```

For each linter NOT pre-installed in the base flavor:

1. Look up its configuration in `custom_linters` section of `linter-sources.yaml`
2. Include all relevant fields (type, package, image, binary_path, target_path, etc.)
3. Add appropriate Renovate annotation based on type:
   - `type: docker_binary` -> Use `image` field with `repo:tag@digest` format, annotate with `# renovate: datasource=docker depName=<source_image>`
   - `type: npm` -> Use `version` field, annotate with `# renovate: datasource=npm depName=<package>`
   - `type: pip` -> Use `version` field, annotate with `# renovate: datasource=pypi depName=<package>`
   - `type: cargo` -> Use `version` field, annotate with `# renovate: datasource=crate depName=<package>`
   - `type: go` -> Use `version` field, annotate with `# renovate: datasource=go depName=<package>`
   - `type: gem` -> Use `version` field, annotate with `# renovate: datasource=rubygems depName=<package>`

**Note**: For docker_binary linters, you need to look up the current digest. Use:

```bash
docker buildx imagetools inspect <source_image>:<version> --format '{{json .Manifest}}' | jq -r '.digest'
```

## Step 6: Report Success

Inform the user:

1. The flavor.yaml has been created at `megalinter-<name>/flavor.yaml`
2. The base flavor selected and why
3. How many custom linters will be installed
4. Next steps:
   - Commit the changes
   - CI will automatically generate Dockerfile and build the image
   - Or run locally: `python megalinter-factory/generate.py megalinter-<name>/`

## Validation Rules Summary

| Check           | Validation                                 |
| --------------- | ------------------------------------------ |
| Name format     | `^[a-z][a-z0-9-]*$`                        |
| Name uniqueness | No existing `megalinter-<name>/` directory |
| Linter keys     | Must exist in `custom_linters` section     |

## Example Output

For `/create-megalinter-flavor test-ci ACTION_ACTIONLINT,MARKDOWN_MARKDOWNLINT`:

```yaml
name: test-ci
description: "Custom MegaLinter for CI testing"

# renovate: datasource=docker depName=oxsecurity/megalinter-ci_light
upstream_image: "oxsecurity/megalinter-ci_light:v9.3.0@sha256:a71e62c83e3b2d52316e7322b9168e1588e9bcf454dbf9b21fc71b0954786e5e"

custom_linters:
  - name: actionlint
    linter_key: ACTION_ACTIONLINT
    type: docker_binary
    # renovate: datasource=docker depName=rhysd/actionlint
    image: "rhysd/actionlint:1.7.10@sha256:ef8299f97635c4c30e2298f48f30763ab782a4ad2c95b744649439a039421e36"
    binary_path: /usr/local/bin/actionlint
    target_path: /usr/bin/actionlint
    version_command: "actionlint --version"
    description: "GitHub Actions workflow linter"

  - name: markdownlint
    linter_key: MARKDOWN_MARKDOWNLINT
    type: npm
    package: markdownlint-cli
    # renovate: datasource=npm depName=markdownlint-cli
    version: "0.44.0"
    version_command: "markdownlint --version"
    description: "Markdown linting"
```
