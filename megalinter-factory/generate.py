#!/usr/bin/env python3
"""
MegaLinter Flavor Factory - Generator Script

Generates Dockerfile and test.sh from a flavor.yaml configuration.
Extracts linter information directly from MegaLinter's descriptors.

Usage:
    python generate.py <flavor-directory>

Example:
    python megalinter-factory/generate.py megalinter-python/
"""

import argparse
import subprocess
import sys
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape

from compose import compose_flavor
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

    if "@" in image_ref:
        image_ref, digest = image_ref.split("@", 1)

    if ":" in image_ref:
        # Handle potential port numbers in registry (e.g., localhost:5000/repo:tag)
        parts = image_ref.rsplit(":", 1)
        if "/" in parts[1] or parts[1].isdigit():
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
        return version_command.split()[0]

    parts = linter_key.split("_")
    if len(parts) > 1:
        return parts[-1].lower()
    return linter_key.lower()


def unique_by_package(linters: list[dict]) -> list[dict]:
    """Keep the first linter per package so a shared package is installed once."""
    seen = set()
    unique = []
    for linter in linters:
        if linter["package"] not in seen:
            seen.add(linter["package"])
            unique.append(linter)
    return unique


def describe_base_linter(key: str, extracted_linters: dict) -> dict:
    """Describe a linter the upstream base image already ships, for the test script."""
    linter_info = extracted_linters.get(key, {})
    version_cmd = linter_info.get("version_command", f"{key.split('_')[-1].lower()} --version")
    return {
        "linter_key": key,
        "name": get_linter_display_name(key, version_cmd),
        "version_command": version_cmd,
    }


def _install_fields(extracted: dict, linter_type: str | None, version: str | None) -> dict:
    """Return the install fields the Dockerfile template needs for this linter type."""
    if linter_type == "docker_binary":
        fields = {
            "binary_path": extracted.get("binary_path"),
            "target_path": extracted.get("target_path"),
            "source_image": extracted.get("source_image"),
            "digest": "",
        }
        if fields["source_image"] and version:
            fields["image"] = f"{fields['source_image']}:{version}"
        return fields

    if linter_type in ("npm", "pip", "go", "cargo"):
        package = extracted.get("package")
        fields = {"package": package}
        if linter_type == "npm":
            fields["npm_packages"] = extracted.get("npm_packages", [package])
        return fields

    if linter_type == "script":
        return {"dockerfile": extracted.get("dockerfile", [])}

    return {}


def resolve_custom_linter(linter_key: str, extracted_linters: dict) -> dict:
    """Describe a linter the flavor installs on top of its upstream base image."""
    extracted = extracted_linters.get(linter_key, {})
    if not extracted:
        raise ValueError(
            f"Linter {linter_key} not found in MegaLinter descriptors. "
            "Shipping the image without it would silently drop a linter - "
            "remove it from custom_linters or fix the key."
        )

    version_cmd = extracted.get("version_command")
    linter_type = extracted.get("type")
    version = extracted.get("version")
    return {
        "linter_key": linter_key,
        "name": get_linter_display_name(linter_key, version_cmd),
        "type": linter_type,
        "version": version,
        "version_command": version_cmd,
        "description": extracted.get("description", ""),
        **_install_fields(extracted, linter_type, version),
        "apk_packages": extracted.get("apk_packages", []),
    }


def resolve_linters(flavor: dict, megalinter_data: dict) -> tuple[list[str], list[dict], list[dict]]:
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
    base_linter_keys = megalinter_data.get("base_flavor_linters", {}).get(base_flavor, [])

    base_linters = [describe_base_linter(key, extracted_linters) for key in base_linter_keys]
    custom_linters = [resolve_custom_linter(key, extracted_linters) for key in flavor.get("custom_linters", [])]

    all_linters = base_linter_keys.copy()
    for linter in custom_linters:
        if linter["linter_key"] not in all_linters:
            all_linters.append(linter["linter_key"])

    return all_linters, base_linters, custom_linters


def derive_upstream_fields(flavor: dict) -> dict:
    """Set the upstream_* fields and base_flavor from upstream_image."""
    if "upstream_image" in flavor:
        parsed = parse_image_ref(flavor["upstream_image"])
        flavor["upstream_repository"] = parsed["repository"]
        flavor["upstream_tag"] = parsed["tag"]
        flavor["upstream_digest"] = parsed["digest"]
        repo_name = parsed["repository"].split("/")[-1]
        if repo_name.startswith("megalinter-"):
            flavor["base_flavor"] = repo_name[len("megalinter-") :]
        elif "base_flavor" not in flavor:
            flavor["base_flavor"] = "ci_light"
    else:
        flavor["upstream_tag"] = flavor.get("upstream_version", "latest")
        flavor["upstream_digest"] = flavor.get("upstream_digest")
    return flavor


def generate_files(flavor_dir: Path, factory_dir: Path) -> None:
    """Generate Dockerfile and test.sh from flavor.yaml."""
    flavor_yaml_path = flavor_dir / "flavor.yaml"
    templates_dir = factory_dir / "templates"

    flavor = compose_flavor(derive_upstream_fields(load_yaml(flavor_yaml_path)), factory_dir)

    print("Extracting linter info from MegaLinter...")
    megalinter_data = get_megalinter_linters()
    print(f"  Found {len(megalinter_data['linters'])} linters in MegaLinter")

    all_linters, base_linters, custom_linters = resolve_linters(flavor, megalinter_data)

    docker_binary_linters = [linter for linter in custom_linters if linter["type"] == "docker_binary"]
    npm_linters = [linter for linter in custom_linters if linter["type"] == "npm"]
    pip_linters = unique_by_package([linter for linter in custom_linters if linter["type"] == "pip"])
    go_linters = [linter for linter in custom_linters if linter["type"] == "go"]
    cargo_linters = [linter for linter in custom_linters if linter["type"] == "cargo"]
    gem_linters = [linter for linter in custom_linters if linter["type"] == "gem"]
    # Script and dockerfile types both use raw dockerfile instructions
    script_linters = [linter for linter in custom_linters if linter["type"] in ("script", "dockerfile")]

    all_apk_packages = sorted({pkg for linter in custom_linters for pkg in linter.get("apk_packages", [])})

    npm_versioned_packages = {}  # package -> (linter_name, version)
    npm_unversioned_packages = set()
    for linter in npm_linters:
        packages = linter.get("npm_packages", [linter["package"]])
        for i, pkg in enumerate(packages):
            if i == 0:
                npm_versioned_packages[pkg] = (linter["name"], linter["version"])
            elif pkg not in npm_versioned_packages:
                npm_unversioned_packages.add(pkg)
    npm_unversioned_packages -= set(npm_versioned_packages.keys())

    env = Environment(
        loader=FileSystemLoader(templates_dir),
        autoescape=select_autoescape(),
        keep_trailing_newline=True,
    )

    context = {
        "flavor": flavor,
        "all_linters": all_linters,
        "base_linters": base_linters,
        "custom_linters_for_test": custom_linters,
        "docker_binary_linters": docker_binary_linters,
        "npm_linters": npm_linters,
        "npm_versioned_packages": npm_versioned_packages,
        "npm_unversioned_packages": sorted(npm_unversioned_packages),
        "pip_linters": pip_linters,
        "go_linters": go_linters,
        "cargo_linters": cargo_linters,
        "gem_linters": gem_linters,
        "script_linters": script_linters,
        "apk_packages": all_apk_packages,
    }

    dockerfile_template = env.get_template("Dockerfile.j2")
    dockerfile_content = dockerfile_template.render(context)
    dockerfile_path = flavor_dir / "Dockerfile"
    dockerfile_path.write_text(dockerfile_content)
    print(f"Generated: {dockerfile_path}")

    testsh_template = env.get_template("test.sh.j2")
    testsh_content = testsh_template.render(context)
    testsh_path = flavor_dir / "test.sh"
    testsh_path.write_text(testsh_content)
    testsh_path.chmod(0o755)
    print(f"Generated: {testsh_path}")

    print(f"\nSuccessfully generated files for {flavor.get('name', 'unknown')} flavor")
    print(f"  Base flavor: {flavor.get('base_flavor', 'ci_light')}")
    print(f"  Total linters: {len(all_linters)}")
    print(f"    - Base: {len(base_linters)}")
    print(f"    - Custom: {len(custom_linters)}")


def flavor_dir_error(flavor_dir: Path) -> str | None:
    """Return why flavor_dir is not a usable flavor directory, or None if it is."""
    if not flavor_dir.is_dir():
        return f"{flavor_dir} is not a directory"
    flavor_yaml = flavor_dir / "flavor.yaml"
    if not flavor_yaml.exists():
        return f"{flavor_yaml} not found"
    return None


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Generate MegaLinter flavor files from flavor.yaml")
    parser.add_argument(
        "flavor_dir",
        type=Path,
        help="Path to flavor directory containing flavor.yaml",
    )
    args = parser.parse_args()

    flavor_dir = args.flavor_dir.resolve()
    factory_dir = Path(__file__).parent.resolve()

    if error := flavor_dir_error(flavor_dir):
        print(f"Error: {error}", file=sys.stderr)
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
