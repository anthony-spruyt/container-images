#!/usr/bin/env python3
"""
MegaLinter Flavor Factory - Generator Script

Generates Dockerfile, test.sh, and metadata.yaml from a flavor.yaml configuration.

Usage:
    python generate.py <flavor-directory>

Example:
    python megalinter-factory/generate.py megalinter-container-images/
"""

import argparse
import sys
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader


def load_yaml(path: Path) -> dict:
    """Load a YAML file and return its contents."""
    with open(path) as f:
        return yaml.safe_load(f) or {}


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
    flavor: dict, linter_sources: dict
) -> tuple[list[str], list[dict], list[dict]]:
    """
    Resolve all linters for a flavor.

    Returns:
        - all_linters: List of all linter keys
        - base_linters: List of base linter info for tests
        - custom_linters: List of custom linter configurations
    """
    base_flavor = flavor.get("base_flavor", "ci_light")
    base_flavor_linters = linter_sources.get("base_flavor_linters", {})
    custom_linter_catalog = linter_sources.get("custom_linters", {})

    # Get base linters - look up version commands from the catalog
    base_linter_keys = base_flavor_linters.get(base_flavor, [])

    base_linters = []
    for key in base_linter_keys:
        # Look up version command from catalog, fallback to conventional pattern
        catalog_entry = custom_linter_catalog.get(key, {})
        fallback_name = key.split("_")[-1].lower() if "_" in key else key.lower()
        version_cmd = catalog_entry.get("version_command", f"{fallback_name} --version")
        display_name = get_linter_display_name(key, version_cmd)
        base_linters.append(
            {
                "linter_key": key,
                "name": display_name,
                "version_command": version_cmd,
            }
        )

    # Process custom linters from flavor.yaml
    custom_linters = []
    for linter_config in flavor.get("custom_linters", []):
        linter_key = linter_config.get("linter_key")
        linter_type = linter_config.get("type")

        # Get defaults from catalog if available
        catalog_entry = custom_linter_catalog.get(linter_key, {})

        # Resolve version command first (needed for display name fallback)
        version_cmd = linter_config.get(
            "version_command", catalog_entry.get("version_command")
        )

        # Merge catalog defaults with flavor-specific overrides
        resolved = {
            "linter_key": linter_key,
            "name": linter_config.get(
                "name", get_linter_display_name(linter_key, version_cmd)
            ),
            "type": linter_type or catalog_entry.get("type"),
            "version": linter_config.get("version", catalog_entry.get("default_version")),
            "version_command": version_cmd,
            "description": linter_config.get(
                "description", catalog_entry.get("description", "")
            ),
        }

        # Type-specific fields
        if resolved["type"] == "docker_binary":
            resolved["source_image"] = linter_config.get(
                "source_image", catalog_entry.get("source_image")
            )
            resolved["binary_path"] = linter_config.get(
                "binary_path", catalog_entry.get("binary_path")
            )
            resolved["target_path"] = linter_config.get(
                "target_path", catalog_entry.get("target_path")
            )
            resolved["digest"] = linter_config.get("digest", "")

        elif resolved["type"] in ("npm", "pip", "go", "cargo"):
            resolved["package"] = linter_config.get("package", catalog_entry.get("package"))

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
    linter_sources_path = factory_dir / "linter-sources.yaml"
    templates_dir = factory_dir / "templates"

    # Load configurations
    flavor = load_yaml(flavor_yaml_path)
    linter_sources = load_yaml(linter_sources_path)

    # Resolve linters
    all_linters, base_linters, custom_linters = resolve_linters(flavor, linter_sources)

    # Group custom linters by type
    docker_binary_linters = [l for l in custom_linters if l["type"] == "docker_binary"]
    npm_linters = [l for l in custom_linters if l["type"] == "npm"]
    pip_linters = [l for l in custom_linters if l["type"] == "pip"]
    go_linters = [l for l in custom_linters if l["type"] == "go"]
    cargo_linters = [l for l in custom_linters if l["type"] == "cargo"]

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

    # Generate metadata.yaml
    metadata_content = f"""---
# Custom MegaLinter flavor: {flavor.get('name', 'unknown')}
# {flavor.get('description', '')}
#
# DO NOT EDIT - Generated from flavor.yaml by megalinter-factory/generate.py
#
# Included linters ({len(all_linters)}):
# - {', '.join(all_linters)}

version: "{flavor.get('upstream_version', 'v9.0.0')}"
auto_patch: true
"""
    metadata_path = flavor_dir / "metadata.yaml"
    metadata_path.write_text(metadata_content)
    print(f"Generated: {metadata_path}")

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

    linter_sources = factory_dir / "linter-sources.yaml"
    if not linter_sources.exists():
        print(f"Error: {linter_sources} not found", file=sys.stderr)
        return 1

    try:
        generate_files(flavor_dir, factory_dir)
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
