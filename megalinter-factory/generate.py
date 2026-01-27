#!/usr/bin/env python3
"""
MegaLinter Flavor Factory - Generator Script

Generates Dockerfile, test.sh, and metadata.yaml from a flavor.yaml configuration.
Extracts linter information directly from MegaLinter's descriptors.

Usage:
    python generate.py <flavor-directory>

Example:
    python megalinter-factory/generate.py megalinter-container-images/
"""

import argparse
import subprocess
import sys
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader

from megalinter_extractor import get_megalinter_linters


def load_yaml(path: Path) -> dict:
    """Load a YAML file and return its contents."""
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def parse_image_ref(image_ref: str) -> dict:
    """
    Parse a Docker image reference into components.

    Handles formats like:
    - 'repo:tag'
    - 'repo:tag@sha256:digest'
    - 'org/repo:tag@sha256:digest'

    Returns dict with: repository, tag, digest (optional)
    """
    digest = None
    tag = "latest"

    # Split off digest first (after @)
    if "@" in image_ref:
        image_ref, digest = image_ref.split("@", 1)

    # Split repository and tag
    if ":" in image_ref:
        # Handle potential port numbers in registry (e.g., localhost:5000/repo:tag)
        parts = image_ref.rsplit(":", 1)
        # Check if the last part looks like a tag (not a port number)
        if "/" in parts[1] or parts[1].isdigit():
            # This is likely a port, not a tag
            repository = image_ref
        else:
            repository = parts[0]
            tag = parts[1]
    else:
        repository = image_ref

    return {
        "repository": repository,
        "tag": tag,
        "digest": digest,
    }


def get_linter_display_name(linter_key: str, version_command: str | None = None) -> str:
    """
    Get display name for a linter.

    Priority:
    1. First word of version_command (e.g., "dotenv-linter" from "dotenv-linter --version")
    2. Last part of linter_key after underscore (e.g., "hadolint" from "DOCKERFILE_HADOLINT")
    """
    if version_command:
        # Extract first word from version command
        first_word = version_command.split()[0]
        return first_word

    # Fallback: use last part of linter key
    parts = linter_key.split("_")
    if len(parts) > 1:
        return parts[-1].lower()
    return linter_key.lower()


def resolve_linters(
    flavor: dict, megalinter_data: dict
) -> tuple[list[str], list[dict], list[dict]]:
    """
    Resolve all linters for a flavor.

    Args:
        flavor: The flavor configuration from flavor.yaml
        megalinter_data: Extracted MegaLinter linter information

    Returns:
        - all_linters: List of all linter keys
        - base_linters: List of base linter info for tests
        - custom_linters: List of custom linter configurations
    """
    base_flavor = flavor.get("base_flavor", "ci_light")
    extracted_linters = megalinter_data.get("linters", {})
    base_flavor_linters = megalinter_data.get("base_flavor_linters", {})

    # Get base linters from extracted MegaLinter data
    base_linter_keys = base_flavor_linters.get(base_flavor, [])

    base_linters = []
    for key in base_linter_keys:
        linter_info = extracted_linters.get(key, {})
        version_cmd = linter_info.get("version_command", f"{key.split('_')[-1].lower()} --version")
        display_name = get_linter_display_name(key, version_cmd)
        base_linters.append(
            {
                "linter_key": key,
                "name": display_name,
                "version_command": version_cmd,
            }
        )

    # Process custom linters from flavor.yaml
    # Support both old format (list of dicts) and new format (list of strings)
    custom_linters = []
    for linter_entry in flavor.get("custom_linters", []):
        # Handle new simple format: just a linter key string
        if isinstance(linter_entry, str):
            linter_key = linter_entry
            linter_config = {}
        else:
            # Handle old format: dict with linter_key and overrides
            linter_key = linter_entry.get("linter_key")
            linter_config = linter_entry

        # Look up linter info from extracted MegaLinter data
        extracted = extracted_linters.get(linter_key, {})

        if not extracted:
            print(f"Warning: Linter {linter_key} not found in MegaLinter descriptors")
            continue

        # Get version command
        version_cmd = linter_config.get(
            "version_command", extracted.get("version_command")
        )

        # Build resolved linter config, allowing flavor.yaml to override
        resolved = {
            "linter_key": linter_key,
            "name": linter_config.get(
                "name", get_linter_display_name(linter_key, version_cmd)
            ),
            "type": linter_config.get("type", extracted.get("type")),
            "version": linter_config.get("version", extracted.get("version")),
            "version_command": version_cmd,
            "description": linter_config.get(
                "description", extracted.get("description", "")
            ),
        }

        # Type-specific fields
        if resolved["type"] == "docker_binary":
            resolved["binary_path"] = linter_config.get(
                "binary_path", extracted.get("binary_path")
            )
            resolved["target_path"] = linter_config.get(
                "target_path", extracted.get("target_path")
            )
            resolved["source_image"] = linter_config.get(
                "source_image", extracted.get("source_image")
            )
            resolved["digest"] = linter_config.get("digest", "")
            # Build full image reference for Dockerfile
            if resolved["source_image"] and resolved["version"]:
                resolved["image"] = f"{resolved['source_image']}:{resolved['version']}"

        elif resolved["type"] in ("npm", "pip", "go", "cargo"):
            resolved["package"] = linter_config.get(
                "package", extracted.get("package")
            )

        elif resolved["type"] == "script":
            # Script-based linters have raw dockerfile instructions
            resolved["dockerfile"] = extracted.get("dockerfile", [])

        # APK dependencies apply to all linter types
        resolved["apk_packages"] = extracted.get("apk_packages", [])

        custom_linters.append(resolved)

    # Build all linters list
    all_linters = base_linter_keys.copy()
    for linter in custom_linters:
        if linter["linter_key"] not in all_linters:
            all_linters.append(linter["linter_key"])

    return all_linters, base_linters, custom_linters


def generate_files(flavor_dir: Path, factory_dir: Path) -> None:
    """Generate Dockerfile, test.sh, and metadata.yaml from flavor.yaml."""
    flavor_yaml_path = flavor_dir / "flavor.yaml"
    templates_dir = factory_dir / "templates"

    # Load flavor configuration
    flavor = load_yaml(flavor_yaml_path)

    # Extract linter info from MegaLinter (clones repo if needed)
    print("Extracting linter info from MegaLinter...")
    megalinter_data = get_megalinter_linters()
    print(f"  Found {len(megalinter_data['linters'])} linters in MegaLinter")

    # Parse upstream_image if present (new format)
    if "upstream_image" in flavor:
        parsed = parse_image_ref(flavor["upstream_image"])
        flavor["upstream_repository"] = parsed["repository"]
        flavor["upstream_tag"] = parsed["tag"]
        flavor["upstream_digest"] = parsed["digest"]
        # Derive base_flavor from repository name (e.g., oxsecurity/megalinter-ci_light -> ci_light)
        repo_name = parsed["repository"].split("/")[-1]
        if repo_name.startswith("megalinter-"):
            flavor["base_flavor"] = repo_name[len("megalinter-"):]
        elif "base_flavor" not in flavor:
            flavor["base_flavor"] = "ci_light"  # Default fallback
    else:
        # Legacy format compatibility
        flavor["upstream_tag"] = flavor.get("upstream_version", "latest")
        flavor["upstream_digest"] = flavor.get("upstream_digest")

    # Resolve linters using extracted MegaLinter data
    all_linters, base_linters, custom_linters = resolve_linters(flavor, megalinter_data)

    # Group custom linters by type
    docker_binary_linters = [l for l in custom_linters if l["type"] == "docker_binary"]
    npm_linters = [l for l in custom_linters if l["type"] == "npm"]
    pip_linters = [l for l in custom_linters if l["type"] == "pip"]
    go_linters = [l for l in custom_linters if l["type"] == "go"]
    cargo_linters = [l for l in custom_linters if l["type"] == "cargo"]
    gem_linters = [l for l in custom_linters if l["type"] == "gem"]
    # Script and dockerfile types both use raw dockerfile instructions
    script_linters = [l for l in custom_linters if l["type"] in ("script", "dockerfile")]

    # Collect all APK dependencies from custom linters (deduplicated)
    all_apk_packages = sorted(set(
        pkg for linter in custom_linters for pkg in linter.get("apk_packages", [])
    ))

    # Set up Jinja2 environment
    env = Environment(loader=FileSystemLoader(templates_dir), keep_trailing_newline=True)

    # Template context
    context = {
        "flavor": flavor,
        "all_linters": all_linters,
        "base_linters": base_linters,
        "custom_linters_for_test": custom_linters,
        "docker_binary_linters": docker_binary_linters,
        "npm_linters": npm_linters,
        "pip_linters": pip_linters,
        "go_linters": go_linters,
        "cargo_linters": cargo_linters,
        "gem_linters": gem_linters,
        "script_linters": script_linters,
        "apk_packages": all_apk_packages,
    }

    # Generate Dockerfile
    dockerfile_template = env.get_template("Dockerfile.j2")
    dockerfile_content = dockerfile_template.render(context)
    dockerfile_path = flavor_dir / "Dockerfile"
    dockerfile_path.write_text(dockerfile_content)
    print(f"Generated: {dockerfile_path}")

    # Generate test.sh
    testsh_template = env.get_template("test.sh.j2")
    testsh_content = testsh_template.render(context)
    testsh_path = flavor_dir / "test.sh"
    testsh_path.write_text(testsh_content)
    testsh_path.chmod(0o755)
    print(f"Generated: {testsh_path}")

    # Generate metadata.yaml only if it doesn't exist (bootstrap only)
    # Version is managed independently - user controls it, auto_patch handles increments
    metadata_path = flavor_dir / "metadata.yaml"
    if not metadata_path.exists():
        metadata_content = f"""---
# Custom MegaLinter flavor: {flavor.get('name', 'unknown')}
# {flavor.get('description', '')}
#
# Version is managed independently of upstream - update manually for major changes.
# auto_patch: true enables automatic patch version increments on rebuild.

version: "v1.0"
auto_patch: true
"""
        metadata_path.write_text(metadata_content)
        print(f"Generated: {metadata_path}")
    else:
        print(f"Skipped: {metadata_path} (already exists, version managed independently)")

    print(f"\nSuccessfully generated files for {flavor.get('name', 'unknown')} flavor")
    print(f"  Base flavor: {flavor.get('base_flavor', 'ci_light')}")
    print(f"  Total linters: {len(all_linters)}")
    print(f"    - Base: {len(base_linters)}")
    print(f"    - Custom: {len(custom_linters)}")


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate MegaLinter flavor files from flavor.yaml"
    )
    parser.add_argument(
        "flavor_dir",
        type=Path,
        help="Path to flavor directory containing flavor.yaml",
    )
    args = parser.parse_args()

    # Resolve paths
    flavor_dir = args.flavor_dir.resolve()
    factory_dir = Path(__file__).parent.resolve()

    # Validate inputs
    if not flavor_dir.is_dir():
        print(f"Error: {flavor_dir} is not a directory", file=sys.stderr)
        return 1

    flavor_yaml = flavor_dir / "flavor.yaml"
    if not flavor_yaml.exists():
        print(f"Error: {flavor_yaml} not found", file=sys.stderr)
        return 1

    try:
        generate_files(flavor_dir, factory_dir)
        return 0
    except FileNotFoundError as e:
        print(f"Error: File not found: {e}", file=sys.stderr)
        return 1
    except yaml.YAMLError as e:
        print(f"Error: Invalid YAML: {e}", file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as e:
        print(f"Error: Command failed: {e}", file=sys.stderr)
        return 1
    except (OSError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
